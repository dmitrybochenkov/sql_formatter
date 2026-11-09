"""Optional Tk UI; one event-loop-owned decision, no background timer threads."""
from math import ceil
from time import monotonic


def select_profile(timeout_seconds=3, difference_count=0):
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise ValueError('Invalid selector timeout')
    import tkinter as tk
    from tkinter import ttk

    root = None
    selected = None
    finished = False
    callback_failed = False
    timer = None
    try:
        root = tk.Tk()
        root.title('SQL Formatter — Выбор профиля')
        root.resizable(False, False)

        def finish(profile=None):
            nonlocal selected, finished, timer
            if finished:
                return
            finished = True
            selected = profile
            if timer is not None:
                root.after_cancel(timer)
                timer = None
            root.quit()

        def callback_error(*_):
            nonlocal callback_failed
            callback_failed = True
            finish()

        def keypress(event):
            if event.char == '1' or event.keysym == 'KP_1':
                finish('personal')
            elif event.char == '2' or event.keysym == 'KP_2':
                finish('corporate')
            elif event.keysym == 'Escape':
                finish()
            else:
                return None
            return 'break'

        def focus():
            try:
                root.lift()
                root.focus_force()
            except tk.TclError:
                pass  # Buttons remain available; timer behaviour is explicit.

        def release_topmost():
            try:
                root.attributes('-topmost', False)
            except tk.TclError:
                pass

        root.report_callback_exception = callback_error
        root.protocol('WM_DELETE_WINDOW', finish)
        root.bind('<KeyPress>', keypress)
        panel = ttk.Frame(root, padding=20)
        panel.pack(fill='both', expand=True)
        for label, profile in (('[1] Personal', 'personal'), ('[2] Corporate', 'corporate')):
            ttk.Button(panel, text=label, takefocus=False,
                       command=lambda value=profile: finish(value)).pack(fill='x', pady=4)
        if difference_count:
            ttk.Label(panel, text=f'Personal: {difference_count} отличий от Corporate').pack()
        countdown = ttk.Label(panel)
        countdown.pack(pady=(8, 0))
        ttk.Label(panel, text='Esc — Cancel').pack(pady=(8, 0))
        root.update_idletasks()
        x = max(0, (root.winfo_screenwidth() - 360) // 2)
        y = max(0, (root.winfo_screenheight() - 240) // 2)
        root.geometry(f'360x240+{x}+{y}')
        root.attributes('-topmost', True)
        root.after(300, release_topmost)
        root.after_idle(focus)
        deadline = monotonic() + timeout_seconds

        def tick():
            nonlocal timer
            timer = None
            if finished:
                return
            remaining = deadline - monotonic()
            if remaining <= 0:
                finish('personal')
                return
            countdown.configure(text=f'Автоматически: Personal через {ceil(remaining)} с')
            timer = root.after(100, tick)

        tick()
        root.mainloop()
        if callback_failed:
            raise RuntimeError('Profile selector callback failed')
        return selected
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass


def show_profile_notice(message):
    """Explicit modal acknowledgement; successful return permits state commit."""
    import tkinter as tk
    from tkinter import messagebox
    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        messagebox.showinfo('SQL Formatter — Personal', message, parent=root)
        return True
    finally:
        if root is not None:
            root.destroy()
