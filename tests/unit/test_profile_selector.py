"""Tk behaviour tests use a fake event loop; never require a display server."""
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dbeaver_profile_selector import select_profile


class FakeTk:
    class TclError(Exception):
        pass

    def __init__(self, event='1', focus_error=False):
        self.event, self.focus_error = event, focus_error
        self.buttons, self.timers, self.topmost = {}, [], []
        self.closed = self.quit_called = self.focus_attempted = False
        self.ttk = SimpleNamespace(Frame=self.widget, Label=self.widget, Button=self.button)

    def Tk(self): return self
    def title(self, value): self.window_title = value
    def resizable(self, *args): pass
    def protocol(self, name, callback): self.close_callback = callback
    def bind(self, name, callback): self.key_callback = callback
    def update_idletasks(self): pass
    def winfo_screenwidth(self): return 1920
    def winfo_screenheight(self): return 1080
    def geometry(self, value): self.position = value
    def attributes(self, name, value): self.topmost.append(value)
    def after(self, delay, callback): self.timers.append(callback)
    def after_idle(self, callback): self.focus_callback = callback
    def lift(self): pass
    def focus_force(self):
        self.focus_attempted = True
        if self.focus_error: raise self.TclError('denied')
    def quit(self): self.quit_called = True
    def destroy(self): self.closed = True
    def widget(self, *args, **kwargs): return SimpleNamespace(pack=lambda **options: None)
    def button(self, *args, **kwargs):
        self.buttons[kwargs['text']] = kwargs['command']
        return self.widget()

    def mainloop(self):
        self.focus_callback()
        for callback in self.timers: callback()
        if self.event == 'close': self.close_callback()
        elif self.event == 'callback-error': self.report_callback_exception(RuntimeError, RuntimeError('secret'), None)
        elif self.event.startswith('mouse:'): self.buttons[self.event[6:]]()
        else:
            self.key_callback(SimpleNamespace(char='x', keysym='x'))
            assert not self.quit_called  # Never auto-select an unknown key.
            self.key_callback(SimpleNamespace(char=self.event, keysym=self.event))


class ProfileSelectorTests(unittest.TestCase):
    def test_keys_cancel_close_and_mouse(self):
        for event, expected in [('1','personal'), ('2','corporate'), ('KP_1','personal'),
                                ('KP_2','corporate'), ('Escape',None), ('close',None),
                                ('mouse:[1] Personal','personal'), ('mouse:[2] Corporate','corporate')]:
            with self.subTest(event=event):
                fake = FakeTk(event)
                with patch.dict(sys.modules, tkinter=fake):
                    self.assertEqual(select_profile(), expected)
                self.assertTrue(fake.closed)
                self.assertTrue(fake.quit_called)
                self.assertTrue(fake.focus_attempted)
                self.assertEqual(fake.topmost, [True, False])

    def test_focus_denied_still_allows_mouse(self):
        fake = FakeTk('mouse:[2] Corporate', focus_error=True)
        with patch.dict(sys.modules, tkinter=fake):
            self.assertEqual(select_profile(), 'corporate')
        self.assertTrue(fake.closed)
        self.assertEqual(fake.topmost[-1], False)

    def test_callback_failure_is_not_success(self):
        fake = FakeTk('callback-error')
        with patch.dict(sys.modules, tkinter=fake), self.assertRaises(RuntimeError):
            select_profile()
        self.assertTrue(fake.closed)

    def test_window_creation_failure(self):
        fake = FakeTk()
        with patch.object(fake, 'Tk', side_effect=fake.TclError('no display')), \
             patch.dict(sys.modules, tkinter=fake), self.assertRaises(fake.TclError):
            select_profile()
