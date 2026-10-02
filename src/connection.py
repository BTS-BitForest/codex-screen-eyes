"""Portable connection settings. Never changes Windows proxy settings."""
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
import winreg

BEGIN = '# BEGIN SCREEN EYES PROXY'
END = '# END SCREEN EYES PROXY'
KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'WS_PROXY', 'WSS_PROXY')


def home():
    return Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))


def read_settings(data):
    try:
        return json.loads((data / 'connection.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'mode': 'auto', 'manual': ''}


def normalize(value):
    value = value.strip()
    if not value or any(c.isspace() for c in value):
        raise ValueError('请填写代理地址，例如 http://127.0.0.1:端口。')
    if '://' not in value:
        value = 'http://' + value
    try:
        uri = urlsplit(value)
        port = uri.port
    except ValueError as error:
        raise ValueError('代理端口必须是 1–65535 的数字。') from error
    if uri.scheme != 'http' or not uri.hostname or uri.username or uri.password or uri.query or uri.fragment or uri.path not in ('', '/'):
        raise ValueError('请使用无用户名密码的 HTTP 代理地址；VPN 的 HTTP / mixed 端口均可。')
    if port is None or not 1 <= port <= 65535:
        raise ValueError('请填写完整代理端口（1–65535）。')
    host = '[' + uri.hostname + ']' if ':' in uri.hostname else uri.hostname
    return f'http://{host}:{port}'


def system_proxy():
    """Use current Windows settings, not stale variables inherited from Codex."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Internet Settings') as key:
            def read(name, default=None):
                try:
                    return winreg.QueryValueEx(key, name)[0]
                except OSError:
                    return default
            if read('ProxyEnable', 0) and read('ProxyServer', ''):
                raw = read('ProxyServer')
                if '=' in raw:
                    entries = dict(part.strip().split('=', 1) for part in raw.split(';') if '=' in part)
                    raw = entries.get('https') or entries.get('http') or ''
                return normalize(raw), 'Windows 系统代理'
            if read('AutoConfigURL', ''):
                raise ValueError('检测到 PAC 自动配置。请选择手动代理，填写 VPN 的 HTTP / mixed 地址，或在可直连网络选择直接连接。')
    except OSError:
        pass
    # Registry values avoid confusing this app's own inherited Codex proxy with a VPN.
    for hive, subkey in ((winreg.HKEY_CURRENT_USER, 'Environment'),
                         (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for name in ('HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY'):
                    try:
                        value = winreg.QueryValueEx(key, name)[0]
                    except OSError:
                        continue
                    if value:
                        return normalize(value), '用户 / 系统代理变量'
        except OSError:
            pass
    return '', '直接连接（也适用于 VPN 的 TUN / 全局隧道）'


def resolve(mode, manual='', detector=None):
    if mode == 'direct':
        return '', '直接连接'
    if mode == 'manual':
        return normalize(manual), '手动代理'
    if mode != 'auto':
        raise ValueError('未知连接模式。')
    return (detector or system_proxy)()


def render_env(original, proxy):
    """Preserve unrelated configuration; remove all old proxy variants."""
    if (BEGIN in original) != (END in original):
        raise ValueError('代理配置区块不完整，请先恢复配置备份。')
    original = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\r?\n?', '', original, flags=re.S)
    kept = []
    for line in original.splitlines():
        match = re.match(r'\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
        if not match or match.group(1).upper() not in KEYS:
            kept.append(line)
    lines = [BEGIN]
    for name in KEYS:
        value = ('localhost,127.0.0.1,::1' if proxy else '*') if name == 'NO_PROXY' else proxy
        lines.append(name + '=' + value)
        lines.append(name.lower() + '=' + value)
    lines.append(END)
    prefix = '\n'.join(kept).rstrip()
    return (prefix + '\n\n' if prefix else '') + '\n'.join(lines) + '\n'


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    os.replace(temporary, path)


def apply(data, mode, manual='', codex_home=None, detector=None):
    proxy, source = resolve(mode, manual, detector)
    if proxy:
        uri = urlsplit(proxy)
        try:
            with socket.create_connection((uri.hostname, uri.port), timeout=3):
                pass
        except OSError as error:
            raise ValueError('代理端口无法连接。请开启 VPN 或更正端口；现有配置未修改。') from error
    location = (codex_home or home()) / '.env'
    old = location.read_text(encoding='utf-8-sig') if location.exists() else ''
    new = render_env(old, proxy)
    changed = old.replace('\r\n', '\n') != new
    if changed:
        if location.exists():
            backup = data / 'backups' / ('codex-env-' + str(time.time_ns()) + '.txt')
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(location, backup)
        atomic_write(location, new)
    atomic_write(data / 'codex-proxy.env', new)
    atomic_write(data / 'connection.json', json.dumps({'mode': mode, 'manual': manual,
        'effective': proxy, 'source': source}, ensure_ascii=False, indent=2))
    return {'proxy': proxy, 'source': source, 'changed': changed}


def probe(mode, manual=''):
    proxy, source = resolve(mode, manual)
    curl = shutil.which('curl.exe') or str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/curl.exe')
    args = [curl, '--silent', '--show-error', '--output', 'NUL', '--connect-timeout', '5', '--max-time', '10',
            '--write-out', '%{http_code}', '--http1.1', '--header', 'Connection: Upgrade', '--header', 'Upgrade: websocket',
            '--header', 'Sec-WebSocket-Version: 13', '--header', 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==']
    args += ['--proxy', proxy, '--noproxy', ''] if proxy else ['--noproxy', '*']
    args += ['https://chatgpt.com/backend-api/codex/realtime']
    result = subprocess.run(args, capture_output=True, timeout=13, creationflags=subprocess.CREATE_NO_WINDOW)
    code = result.stdout.decode('ascii', errors='replace').strip()
    if result.returncode:
        return f'{source}：连接失败，请检查网络或代理。'
    return f'{source}：已收到服务器响应（HTTP {code}）。这项检测不代表语音鉴权已成功。'


def powershell():
    return shutil.which('pwsh') or str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')


def open_codex():
    script = Path(__file__).with_name('activate-codex.ps1')
    environment = os.environ.copy()
    base = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
    environment['SCREEN_EYES_DATA'] = str(base / 'data')
    result = subprocess.run([powershell(), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-Json'],
        capture_output=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW, env=environment)
    raw = result.stdout.decode('utf-8-sig', errors='replace').strip()
    if not raw:
        raise ValueError('Windows 未返回启动结果，请从开始菜单打开 Codex。')
    reply = json.loads(raw)
    if reply.get('status') == 'error':
        raise ValueError(reply.get('message', 'Codex 启动失败。'))
    return '已打开 Codex。' if reply.get('WindowFound') else '已请求 Windows 打开 Codex，暂未检测到窗口。'


def find_cli():
    found = shutil.which('codex.exe')
    if found:
        return found
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'OpenAI/Codex/bin'
    candidates = list(base.glob('*/codex.exe'))
    if candidates:
        return str(max(candidates, key=lambda p: p.stat().st_mtime))
    raise ValueError('未找到 Codex 后台程序。请先安装并打开一次 Codex。')


def connect(executable):
    cli = find_cli()
    # CLI owns config writing; never splice the user's TOML by hand.
    result = subprocess.run([cli, 'mcp', 'add', 'screen-eyes', '--', str(executable), 'serve'],
        capture_output=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise ValueError('连接配置失败：' + result.stderr.decode('utf-8', errors='replace')[-500:])
    return '已连接 Codex。请新建聊天使用；如工具仍未出现，再完整退出并打开 Codex。'
