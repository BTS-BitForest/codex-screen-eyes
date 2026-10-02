"""Self-contained Windows installer using the official Codex plugin CLI."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import threading
import zipfile

MARKET = 'bitforest-screen-eyes'
SELECTOR = 'screen-eyes@' + MARKET
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def find_codex():
    import shutil
    root = Path(os.environ.get('LOCALAPPDATA', '')) / 'OpenAI/Codex/bin'
    candidates = list(root.glob('*/codex.exe')) if root.exists() else []
    if candidates:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    command = shutil.which('codex.exe')
    if command:
        return Path(command)
    raise RuntimeError('没有找到 Codex。请先安装并打开官方桌面应用，再运行安装器。')


def execute(cli, arguments, environment):
    result = subprocess.run([str(cli)] + arguments, env=environment,
        capture_output=True, encoding='utf-8', errors='replace',
        timeout=90, creationflags=FLAGS)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[:1800])
    try:
        return json.loads(result.stdout)
    except ValueError:
        return result.stdout.strip()


def install(destination, codex_home=None, progress=lambda _: None):
    cli = find_codex()
    environment = os.environ.copy()
    if codex_home:
        location = Path(codex_home).resolve()
        location.mkdir(parents=True, exist_ok=True)
        environment['CODEX_HOME'] = str(location)
    progress('正在检查 Codex 插件支持…')
    execute(cli, ['plugin', 'marketplace', 'list', '--json'], environment)
    # Old direct MCP registration shadows a plugin: never silently remove it.
    servers = execute(cli, ['mcp', 'list', '--json'], environment)
    if isinstance(servers, list) and any(s.get('name') == 'screen-eyes' and
            not (s.get('transport', {}).get('env') or {}).get('PLUGIN_ROOT') for s in servers):
        raise RuntimeError('检测到旧的 screen-eyes 直接 MCP 注册。它可能覆盖插件。请先备份配置并让 Codex 帮你迁移；安装器没有删除任何旧配置。')
    runtime = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    payload = runtime / 'screen-eyes-payload.zip'
    expected = (runtime / 'screen-eyes-payload.sha256').read_text(encoding='ascii').strip()
    if hashlib.sha256(payload.read_bytes()).hexdigest() != expected:
        raise RuntimeError('安装包校验失败，请重新下载完整安装器。')
    base = Path(destination).resolve()
    progress('正在写入插件文件…')
    plugin = base / 'plugins/screen-eyes'
    with zipfile.ZipFile(payload) as bundle:
        assert bundle.testzip() is None, '损坏的 ZIP'
        for member in bundle.infolist():
            relative = PurePosixPath(member.filename)
            if relative.is_absolute() or '..' in relative.parts or ':' in member.filename:
                raise RuntimeError('安装包包含无效路径。')
            target = (plugin / member.filename).resolve()
            if plugin not in target.parents:
                raise RuntimeError('安装包路径越界。')
            if not member.is_dir():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(member))
    catalog = base / '.agents/plugins/marketplace.json'
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(json.dumps({'name': MARKET, 'interface': {'displayName': 'Bitforest 屏幕眼睛'},
        'plugins': [{'name': 'screen-eyes', 'source': {'source': 'local', 'path': './plugins/screen-eyes'},
            'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
            'category': 'Productivity'}]}, ensure_ascii=False, indent=2), encoding='utf-8')
    progress('正在通过 Codex 安装插件…')
    execute(cli, ['plugin', 'marketplace', 'add', str(base), '--json'], environment)
    result = execute(cli, ['plugin', 'add', SELECTOR, '--json'], environment)
    # Resolve installed cache path and the real plugin data directory, rather than
    # launching the source EXE with an unrelated default state directory.
    servers = execute(cli, ['mcp', 'list', '--json'], environment)
    matching = [s for s in servers if 'screen-eyes' in s.get('name', '') and
                (s.get('transport', {}).get('env') or {}).get('SCREEN_EYES_STATE')]
    if not matching:
        raise RuntimeError('文件已安装，但 Codex 没有返回插件工具入口。请更新 Codex，并检查组织插件策略。')
    found = next((s for s in matching if MARKET in
                 (s.get('transport', {}).get('env') or {}).get('PLUGIN_ROOT', '')), None)
    if found is None:
        raise RuntimeError('检测到其他来源的同名插件覆盖此安装。请在插件设置中只启用需要的 screen-eyes 来源；没有删除其他插件。')
    transport = found['transport']
    executable = transport['command']
    state = transport['env']['SCREEN_EYES_STATE']
    config = {'executable': executable, 'state': state, 'selector': SELECTOR}
    (base / 'installed.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'installed': True, 'root': str(base), 'codex': str(cli), 'plugin': result, 'resolved': config}


def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    window = tk.Tk()
    window.title('Bitforest 屏幕眼睛 · 快速安装')
    window.geometry('620x410')
    window.configure(bg='#f1f5f9')
    ttk.Label(window, text='给 Codex 语音配上眼睛', font=('Microsoft YaHei UI', 21, 'bold')).pack(pady=(28, 12))
    ttk.Label(window, text='Windows 本地插件 · 无需管理员权限或 Python\n自动安装插件；首次共享仍由你选择屏幕并明确开启。', justify='center').pack(pady=8)
    path = tk.StringVar(value=str(Path(os.environ['LOCALAPPDATA']) / 'Bitforest/ScreenEyes'))
    frame = ttk.Frame(window)
    frame.pack(fill='x', padx=24, pady=14)
    ttk.Entry(frame, textvariable=path).pack(side='left', fill='x', expand=True)
    def choose():
        picked = filedialog.askdirectory(title='选择安装目录')
        if picked: path.set(picked)
    ttk.Button(frame, text='选择目录', command=choose).pack(side='left', padx=(8, 0))
    status = tk.StringVar(value='需要先安装并运行过 Codex 桌面应用。')
    ttk.Label(window, textvariable=status, wraplength=560, justify='center').pack(padx=24, pady=12)
    def run():
        target = path.get().strip()
        if not target: return
        button.config(state='disabled')
        def update(value): window.after(0, lambda: status.set(value))
        def worker():
            try:
                install(target, progress=update)
                update('安装完成！新建 Codex 聊天，打开 screen-eyes 共享设置。\n选择来源并开启自动共享，再开始新的语音聊天。\n若插件未加载，请自行完整退出并重新打开 Codex。')
            except Exception as error:
                message = str(error)
                update('安装未完成：'+message)
                window.after(0, lambda: button.config(state='normal'))
        threading.Thread(target=worker, daemon=True).start()
    button = ttk.Button(window, text='安装屏幕眼睛', command=run)
    button.pack(pady=14)
    ttk.Label(window, text='不会关闭 Codex、修改代理或自动开启共享。', foreground='#64748b').pack()
    window.mainloop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--root')
    parser.add_argument('--codex-home')
    args = parser.parse_args()
    if args.install:
        try:
            result = install(args.root, args.codex_home)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as error:
            print(str(error), file=sys.stderr, flush=True)
            sys.exit(1)
    else:
        gui()
