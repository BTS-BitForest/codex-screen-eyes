"""Single Windows companion with explicit sharing and portable connection settings."""
import ctypes
from ctypes import wintypes as W
import io
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk
import uuid
from PIL import Image, ImageTk
import connection

TITLE = 'Codex 语音伴侣'
MODES = {'自动检测': 'auto', '直接连接': 'direct', '手动代理': 'manual'}


def run(eyes):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, W.BOOL, W.LPCWSTR]
    kernel.CreateMutexW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    mutex = kernel.CreateMutexW(None, False, 'Local\\CodexScreenEyesPanel')
    if ctypes.get_last_error() == 183:
        for source in eyes.windows():
            if source['label'] == TITLE:
                eyes.U.ShowWindow(W.HWND(source['hwnd']), 9)
                eyes.U.SetForegroundWindow(W.HWND(source['hwnd']))
                break
        kernel.CloseHandle(mutex)
        return
    if not eyes.read_state().get('voice_session'):
        eyes.pause()
    root = tk.Tk()
    root.title(TITLE)
    root.geometry(f"940x{min(970, root.winfo_screenheight()-100)}")
    root.minsize(800, 600)
    icon = Path(__file__).with_name('screen-eyes.ico')
    if icon.exists():
        root.iconbitmap(str(icon))
    root.configure(bg='#edf2f7')
    font = ('Microsoft YaHei UI', 10)
    root.option_add('*Font', font)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TFrame', background='#ffffff')
    style.configure('TLabel', background='#ffffff', foreground='#172d46', font=font)
    style.configure('Muted.TLabel', foreground='#657990')
    style.configure('Title.TLabel', font=('Microsoft YaHei UI', 17, 'bold'))
    style.configure('TNotebook', background='#edf2f7', borderwidth=0)
    style.configure('TNotebook.Tab', padding=(28, 12), font=font, background='#e2e9f1')
    style.map('TNotebook.Tab', background=[('selected', '#ffffff')], foreground=[('selected', '#007f73')])
    style.configure('TButton', padding=(16, 10), font=font, borderwidth=0, background='#e9eff5')
    style.map('TButton', background=[('active', '#d7e3ee')])
    style.configure('Primary.TButton', background='#087f73', foreground='white')
    style.map('Primary.TButton', background=[('active', '#08665e'), ('disabled', '#91bdb7')])
    style.configure('TCombobox', padding=8)
    style.configure('TEntry', padding=8)
    header = tk.Frame(root, bg='#12283e', padx=28, pady=21)
    header.pack(fill='x')
    tk.Label(header, text='◉  '+TITLE, font=('Microsoft YaHei UI', 21, 'bold'), bg='#12283e', fg='white').pack(anchor='w')
    tk.Label(header, text='让对话看见你的屏幕', bg='#12283e', fg='#b1c9db').pack(anchor='w', pady=(4, 0))
    tk.Label(root, text='本地按需截图  ·  跟随语音  ·  Windows 插件测试版 0.4', bg='#edf2f7', fg='#64788d').pack(side='bottom', pady=(0, 12))
    tabs = ttk.Notebook(root)
    tabs.pack(fill='both', expand=True, padx=24, pady=(20, 10))
    scroll_canvases = []
    def page(label):
        outer = ttk.Frame(tabs)
        canvas = tk.Canvas(outer, bg='white', highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = ttk.Frame(canvas, padding=24)
        item = canvas.create_window(0, 0, window=inner, anchor='nw')
        inner.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        tabs.add(outer, text=label)
        scroll_canvases.append(canvas)
        return inner
    share = page('屏幕共享')
    network = page('连接设置')
    root.bind('<MouseWheel>', lambda event: scroll_canvases[tabs.index('current')].yview_scroll(-int(event.delta/120), 'units'))
    ttk.Label(share, text='选择你想一起看的画面', style='Title.TLabel').pack(anchor='w')
    ttk.Label(share, text='共享开启后，在 Codex 原生语音中说：“看看我的屏幕。”', style='Muted.TLabel').pack(anchor='w', pady=(8, 18))
    chooser = ttk.Combobox(share, state='readonly')
    chooser.pack(fill='x')
    sources = []
    preview = tk.Canvas(share, height=205, bg='#f0f5f8', highlightthickness=0)
    preview.pack(fill='x', pady=16)
    preview.image_ref = None
    def placeholder(text='画面由你掌控\n点击开始共享，Codex 才能获取截图'):
        preview.delete('all')
        preview.image_ref = None
        preview.create_text(max(preview.winfo_width(), 680)//2, 103, text=text, justify='center',
                            font=('Microsoft YaHei UI', 12), fill='#61798b')
    share_status = tk.StringVar(value='● 已暂停 · 没有采集屏幕')
    automatic = tk.BooleanVar(value=bool(eyes.read_state().get('auto_voice')))
    def auto_changed():
        state = eyes.read_state()
        state.update(auto_voice=automatic.get(), enabled=False, revision=uuid.uuid4().hex)
        state.pop('voice_session', None)
        if automatic.get() and chooser.current() >= 0:
            state['source'] = sources[chooser.current()]
        eyes.save_state(state)
        if automatic.get():
            import voice_watch
            voice_watch.ensure(eyes)
            share_status.set('● 等待下一次语音开始 · 可以关闭此设置窗口')
        else:
            share_status.set('● 已关闭语音自动共享')
    ttk.Checkbutton(share, text='跟随语音自动共享（实验功能，最长 4 小时）', variable=automatic,
                    command=auto_changed).pack(anchor='w', pady=(0, 10), before=preview)
    def stop():
        eyes.pause()
        share_status.set('● 已暂停 · 没有采集屏幕')
        placeholder()
    def refresh():
        previous = sources[chooser.current()] if 0 <= chooser.current() < len(sources) else None
        sources[:] = eyes.monitors() + [s for s in eyes.windows() if s['label'] != TITLE]
        chooser['values'] = [s['label'] for s in sources]
        if sources:
            chooser.current(sources.index(previous) if previous in sources else 0)
    def show_preview():
        try:
            _, png = eyes.capture({'max_side': 1000})
            frame = Image.open(io.BytesIO(png))
            frame.thumbnail((max(preview.winfo_width()-20, 200), 195))
            preview.image_ref = ImageTk.PhotoImage(frame)
            preview.delete('all')
            preview.create_image(preview.winfo_width()//2, 103, image=preview.image_ref)
        except Exception:
            placeholder('请先开始共享，再预览所选画面')
    def start():
        if chooser.current() < 0:
            return
        source = sources[chooser.current()]
        state = eyes.read_state()
        state.pop('voice_session', None)
        state.update(enabled=True, source=source, revision=uuid.uuid4().hex)
        eyes.save_state(state)
        share_status.set('● 正在共享 · '+source['label'])
        placeholder('共享已开启\n可点击“预览画面”检查共享范围')
    def source_changed(_):
        stop()
        if automatic.get():
            auto_changed()
    chooser.bind('<<ComboboxSelected>>', source_changed)
    actions = ttk.Frame(share)
    actions.pack(fill='x')
    for label, command, button_style in [('开始共享', start, 'Primary.TButton'), ('暂停', stop, 'TButton'),
                                         ('预览画面', show_preview, 'TButton'), ('刷新窗口', refresh, 'TButton')]:
        ttk.Button(actions, text=label, command=command, style=button_style).pack(side='left', padx=(0, 8))
    ttk.Label(share, textvariable=share_status, wraplength=690, foreground='#087f73').pack(anchor='w', pady=(20, 12))
    ttk.Separator(share).pack(fill='x', pady=(0, 14))
    ttk.Label(share, text='窗口被遮挡时，遮挡内容也可能出现在截图中。\n自动模式可关闭设置窗口，后台继续等待语音；手动共享在窗口关闭时停止。',
              style='Muted.TLabel', wraplength=690).pack(anchor='w')
    ttk.Label(network, text='适应你现在的网络', style='Title.TLabel').pack(anchor='w')
    ttk.Label(network, text='无需记住固定端口，也无需安装额外的代理软件。', style='Muted.TLabel').pack(anchor='w', pady=(8, 16))
    settings = connection.read_settings(eyes.STATE.parent)
    mode = tk.StringVar(value=next((k for k,v in MODES.items() if v == settings.get('mode')), '自动检测'))
    manual = tk.StringVar(value=settings.get('manual', ''))
    mode_select = ttk.Combobox(network, textvariable=mode, values=list(MODES), state='readonly')
    mode_select.pack(fill='x')
    manual_entry = ttk.Entry(network, textvariable=manual)
    manual_entry.pack(fill='x', pady=(10, 6))
    hint = tk.StringVar()
    def mode_changed(_=None):
        manual_entry.configure(state='normal' if mode.get() == '手动代理' else 'disabled')
        hint.set({'自动检测': '读取 Windows 当前代理；未设置时直连。更换 VPN 后重新保存即可。',
                  '直接连接': '适合无需代理的网络，或 VPN 的 TUN 模式。覆盖 Codex 中残留的旧代理。',
                  '手动代理': '填写 VPN 的 HTTP / mixed 地址，例如 http://127.0.0.1:端口。'}[mode.get()])
    mode_select.bind('<<ComboboxSelected>>', mode_changed)
    mode_changed()
    ttk.Label(network, textvariable=hint, style='Muted.TLabel', wraplength=690).pack(anchor='w', pady=(0, 14))
    network_status = tk.StringVar(value='保存连接设置后生效；设置变更需要完整退出并重新打开 Codex。')
    status_label = ttk.Label(network, textvariable=network_status, wraplength=690, foreground='#087f73')
    status_label.pack(anchor='w', pady=(0, 14))
    updates = queue.Queue()
    busy = False
    buttons = []
    def work(action, selected, address):
        try:
            if action == 'probe':
                message = connection.probe(selected, address)
            elif action == 'connect':
                if not getattr(sys, 'frozen', False):
                    raise ValueError('请使用打包后的 EXE 连接 Codex。开发版本已通过本地插件连接。')
                message = connection.connect(Path(sys.executable))
            else:
                result = connection.apply(eyes.STATE.parent, selected, address)
                message = result['source'] + ' · ' + (result['proxy'] or '无需代理')
                message += '\n已保存。请完整退出并重新打开 Codex，使后台读取新设置。' if result['changed'] else '\n配置未改变，无需因本次保存重启。'
                if action == 'open':
                    message += '\n' + connection.open_codex()
            updates.put((message, False))
        except Exception as error:
            updates.put((str(error), True))
    def begin(action):
        nonlocal busy
        if busy:
            return
        busy = True
        for button in buttons:
            button.state(['disabled'])
        network_status.set('正在处理…')
        threading.Thread(target=work, args=(action, MODES[mode.get()], manual.get()), daemon=True).start()
    row = ttk.Frame(network)
    row.pack(fill='x')
    for label, action, button_style in [('保存设置', 'save', 'Primary.TButton'), ('检测连接', 'probe', 'TButton'), ('打开 Codex', 'open', 'TButton')]:
        button = ttk.Button(row, text=label, command=lambda a=action: begin(a), style=button_style)
        button.pack(side='left', padx=(0, 8))
        buttons.append(button)
    ttk.Separator(network).pack(fill='x', pady=20)
    ttk.Label(network, text='首次在这台电脑使用？', font=('Microsoft YaHei UI', 12, 'bold')).pack(anchor='w')
    ttk.Label(network, text='先把本应用放在固定文件夹，再连接 Codex。已经安装 screen-eyes 插件则无需重复连接。',
              style='Muted.TLabel', wraplength=690).pack(anchor='w', pady=(6, 10))
    button = ttk.Button(network, text='连接到 Codex', command=lambda: begin('connect'))
    button.pack(anchor='w')
    buttons.append(button)
    ttk.Label(network, text='设置只作用于 Codex，不更改 Windows 系统代理。\n自动检测不持续监控 VPN；切换网络后请重新保存。PAC 和 SOCKS-only 代理需另行配置 HTTP / mixed 入口。',
              style='Muted.TLabel', wraplength=690).pack(anchor='w', pady=(14, 0))
    def poll():
        nonlocal busy
        try:
            message, error = updates.get_nowait()
        except queue.Empty:
            pass
        else:
            busy = False
            network_status.set(message)
            status_label.configure(foreground='#b54338' if error else '#087f73')
            for button in buttons:
                button.state(['!disabled'])
        root.after(120, poll)
    def heartbeat():
        eyes.HEARTBEAT.touch()
        state = eyes.read_state()
        if state.get('enabled') and state.get('voice_session'):
            share_status.set('● 语音中 · 正在共享 '+state.get('source', {}).get('label', ''))
        elif not state.get('enabled'):
            share_status.set('● 自动模式 · 等待下一次语音开始' if state.get('auto_voice') else '● 已暂停 · 没有采集屏幕')
            if preview.image_ref is not None:
                placeholder()
        root.after(1000, heartbeat)
    def close():
        if not (eyes.read_state().get('auto_voice') and eyes.read_state().get('voice_session')):
            stop()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    refresh()
    saved_source = eyes.read_state().get('source')
    if saved_source in sources:
        chooser.current(sources.index(saved_source))
    if automatic.get():
        import voice_watch
        voice_watch.ensure(eyes)
    heartbeat()
    poll()
    root.after(120, placeholder)
    try:
        root.mainloop()
    finally:
        if not (eyes.read_state().get('auto_voice') and eyes.read_state().get('voice_session')):
            eyes.pause()
        kernel.CloseHandle(mutex)
