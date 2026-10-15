"""Optional Tk UI. Importing this module never imports Tk or opens a window."""


def select_profile():
    import tkinter as tk
    from tkinter import ttk

    root = None
    selected = None
    callback_failed = False
    try:
        root = tk.Tk()
        root.title('SQL Formatter')
        root.resizable(False, False)

        def finish(profile=None):
            nonlocal selected
            selected = profile
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
            # Windows may deny foreground activation; clickable buttons remain.
            try:
                root.lift()
                root.focus_force()
            except tk.TclError:
                pass

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
        ttk.Label(panel, text='Esc — Cancel').pack(pady=(12, 0))
        root.update_idletasks()
        x = max(0, (root.winfo_screenwidth() - 300) // 2)
        y = max(0, (root.winfo_screenheight() - 180) // 2)
        root.geometry(f'300x180+{x}+{y}')
        root.attributes('-topmost', True)
        root.after(300, release_topmost)
        root.after_idle(focus)
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
