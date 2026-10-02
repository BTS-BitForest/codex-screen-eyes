"""Experimental local voice lifecycle adapter. No audio/transcript retention."""
import ctypes
from ctypes import wintypes as W
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def event(line):
    try:
        record = json.loads(line)
        payload = record.get('payload', {})
        if record.get('type') != 'realtime_item':
            return None
        kind = payload.get('type')
        session = payload.get('realtime_session_id')
        if kind not in ('realtime_session_started', 'realtime_session_closed') or not session:
            return None
        when = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00')).timestamp()
        return kind, session, when
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


class Lifecycle:
    def __init__(self, eyes, since):
        self.eyes = eyes
        self.since = since
        self.active = {}

    def accept(self, value):
        if not value:
            return
        kind, session, when = value
        if when < self.since:
            return
        eyes = self.eyes
        state = eyes.read_state()
        if kind == 'realtime_session_started':
            if session in self.active:
                return
            self.active[session] = when
            if state.get('auto_voice') and state.get('source'):
                try:
                    eyes.bounds(state['source'])
                except (ValueError, KeyError):
                    return
                state.update(enabled=True, voice_session=session, revision=uuid.uuid4().hex)
                eyes.save_state(state)
                eyes.VOICE_HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
                eyes.VOICE_HEARTBEAT.touch()
        else:
            self.active.pop(session, None)
            if state.get('voice_session') == session:
                eyes.pause()

    def tick(self, desktop_alive=True, readable=True):
        eyes = self.eyes
        state = eyes.read_state()
        session = state.get('voice_session')
        if not state.get('enabled') or not session:
            return
        valid = desktop_alive and readable and state.get('auto_voice') and session in self.active
        # Bound unattended sharing even if a future client stops recording the close event.
        valid = valid and time.time() - self.active.get(session, 0) < 4 * 3600
        if valid:
            eyes.VOICE_HEARTBEAT.touch()
        else:
            eyes.pause()


class Tail:
    def __init__(self, folder):
        self.folder = folder
        self.positions = {}
        # Never replay an already-open voice session when the watcher starts.
        for path in folder.rglob('*.jsonl'):
            try:
                self.positions[path] = (path.stat().st_size, b'')
            except OSError:
                pass

    def poll(self):
        rows = []
        for path in self.folder.rglob('*.jsonl'):
            try:
                size = path.stat().st_size
                offset, partial = self.positions.get(path, (0, b''))
                if size < offset:
                    offset, partial = size, b''
                if size == offset:
                    continue
                with path.open('rb') as stream:
                    stream.seek(offset)
                    chunk = stream.read(2 * 1024 * 1024)
                    offset = stream.tell()
                lines = (partial + chunk).split(b'\n')
                self.positions[path] = (offset, lines.pop())
                for line in lines:
                    # Don't JSON-decode unrelated conversation contents.
                    if b'realtime_session_started' in line or b'realtime_session_closed' in line:
                        value = event(line)
                        if value:
                            rows.append(value)
            except OSError:
                # An inaccessible active log is not a signal that sharing may continue.
                return [], False
        readable = self.folder.exists() and all(p.exists() for p in self.positions)
        return sorted(rows, key=lambda row: row[2]), readable


def desktop_alive():
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', W.DWORD),
                    ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                    ('pcPriClassBase', W.LONG), ('dwFlags', W.DWORD), ('szExeFile', W.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
    kernel.Process32FirstW.argtypes = [W.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return False
    try:
        row = Entry()
        row.dwSize = ctypes.sizeof(row)
        valid = kernel.Process32FirstW(snapshot, ctypes.byref(row))
        while valid:
            if row.szExeFile.lower() == 'chatgpt.exe':
                return True
            valid = kernel.Process32NextW(snapshot, ctypes.byref(row))
        return False
    finally:
        kernel.CloseHandle(snapshot)


def ensure(eyes):
    if not eyes.read_state().get('auto_voice'):
        return
    heartbeat = eyes.STATE.with_suffix('.watch-heartbeat')
    try:
        if time.time() - heartbeat.stat().st_mtime < 4:
            return
    except OSError:
        pass
    args = [sys.executable, 'watch'] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(eyes.__file__)), 'watch']
    environment = os.environ.copy()
    environment['SCREEN_EYES_STATE'] = str(eyes.STATE)
    # Detached onefile child must own its extraction directory, independently of MCP.
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=environment, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)


def run(eyes):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, W.BOOL, W.LPCWSTR]
    kernel.CreateMutexW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    name = 'Local\\ScreenEyesVoiceWatch-' + __import__('hashlib').sha256(str(eyes.STATE).encode()).hexdigest()[:12]
    mutex = kernel.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(mutex)
        return
    state = eyes.read_state()
    if state.get('voice_session'):
        eyes.pause()
    folder = Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex'))) / 'sessions'
    since = time.time()
    tail = Tail(folder)
    lifecycle = Lifecycle(eyes, since)
    try:
        while eyes.read_state().get('auto_voice'):
            eyes.STATE.with_suffix('.watch-heartbeat').touch()
            alive = desktop_alive()
            rows, readable = tail.poll()
            for row in rows:
                lifecycle.accept(row)
            lifecycle.tick(alive, readable)
            if not alive:
                break
            time.sleep(1)
    finally:
        if eyes.read_state().get('voice_session'):
            eyes.pause()
        kernel.CloseHandle(mutex)
