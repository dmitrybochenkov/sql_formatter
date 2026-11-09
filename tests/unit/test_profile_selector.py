"""Tk behaviour tests use a fake event loop; never require a display server."""
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from formatter_modules.profile_selector import select_profile


class FakeTk:
    class TclError(Exception):
        pass

    def __init__(self, event='1', focus_error=False):
        self.event, self.focus_error = event, focus_error
        self.buttons, self.timers, self.topmost = {}, {}, []
        self.now = 0.0
        self.serial = 0
        self.cancelled = []
        self.labels = []
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
    def after(self, delay, callback):
        self.serial += 1
        self.timers[self.serial] = (self.now + delay / 1000, callback)
        return self.serial
    def after_cancel(self, handle):
        self.cancelled.append(handle)
        self.timers.pop(handle, None)
    def advance(self, end):
        while self.timers and not self.quit_called:
            handle = min(self.timers, key=lambda h: self.timers[h][0])
            when, callback = self.timers[handle]
            if when > end: break
            self.now = when
            del self.timers[handle]
            callback()
        self.now = end
    def after_idle(self, callback): self.focus_callback = callback
    def lift(self): pass
    def focus_force(self):
        self.focus_attempted = True
        if self.focus_error: raise self.TclError('denied')
    def quit(self): self.quit_called = True
    def destroy(self): self.closed = True
    def widget(self, *args, **kwargs):
        self.labels.append(kwargs.get('text', ''))
        return SimpleNamespace(pack=lambda **options: None,
                               configure=lambda **options: self.labels.append(options.get('text', '')))
    def button(self, *args, **kwargs):
        self.buttons[kwargs['text']] = kwargs['command']
        return self.widget()

    def mainloop(self):
        self.focus_callback()
        self.advance(0.3)
        if self.event == 'timeout': self.advance(65)
        elif self.event == 'manual-race':
            callback = next(iter(self.timers.values()))[1]
            self.now = 3.0
            self.key_callback(SimpleNamespace(char='2', keysym='2'))
            callback()  # An already queued timeout cannot override a decision.
        elif self.event == 'timer-race':
            self.advance(3.1)
            self.key_callback(SimpleNamespace(char='2', keysym='2'))
        elif self.event == 'close': self.close_callback()
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
                with patch.dict(sys.modules, tkinter=fake), patch('formatter_modules.profile_selector.monotonic', side_effect=lambda: fake.now):
                    self.assertEqual(select_profile(), expected)
                self.assertTrue(fake.closed)
                self.assertTrue(fake.quit_called)
                self.assertTrue(fake.focus_attempted)
                self.assertEqual(fake.topmost, [True, False])

    def test_focus_denied_still_allows_mouse(self):
        fake = FakeTk('mouse:[2] Corporate', focus_error=True)
        with patch.dict(sys.modules, tkinter=fake), patch('formatter_modules.profile_selector.monotonic', side_effect=lambda: fake.now):
            self.assertEqual(select_profile(), 'corporate')
        self.assertTrue(fake.closed)
        self.assertEqual(fake.topmost[-1], False)

    def test_callback_failure_is_not_success(self):
        fake = FakeTk('callback-error')
        with patch.dict(sys.modules, tkinter=fake), patch('formatter_modules.profile_selector.monotonic', side_effect=lambda: fake.now), self.assertRaises(RuntimeError):
            select_profile()
        self.assertTrue(fake.closed)

    def test_window_creation_failure(self):
        fake = FakeTk()
        with patch.object(fake, 'Tk', side_effect=fake.TclError('no display')), \
             patch.dict(sys.modules, tkinter=fake), self.assertRaises(fake.TclError):
            select_profile()

    def test_notice_acknowledgement_and_failure_destroy_root(self):
        from formatter_modules.profile_selector import show_profile_notice
        from unittest.mock import Mock
        for failure in (False, True):
            fake=FakeTk()
            fake.withdraw=lambda:None
            fake.messagebox=SimpleNamespace(showinfo=Mock(side_effect=RuntimeError() if failure else None))
            with patch.dict(sys.modules,tkinter=fake):
                if failure:
                    with self.assertRaises(RuntimeError):show_profile_notice('Настройки корректны')
                else:
                    self.assertTrue(show_profile_notice('Настройки корректны'))
            self.assertTrue(fake.closed)
            fake.messagebox.showinfo.assert_called_once()


class ProfileTimerTests(unittest.TestCase):
    def test_timeout_countdown_and_race_single_decision(self):
        for event, expected in [('timeout', 'personal'), ('manual-race', 'corporate'),
                                ('timer-race', 'personal'), ('Escape', None), ('close', None)]:
            fake = FakeTk(event)
            with self.subTest(event=event), patch.dict(sys.modules, tkinter=fake), \
                 patch('formatter_modules.profile_selector.monotonic', side_effect=lambda: fake.now):
                self.assertEqual(select_profile(3, 2), expected)
            self.assertTrue(fake.closed)
            self.assertIn('Personal: 2 отличий от Corporate', fake.labels)
            self.assertIn('Автоматически: Personal через 3 с', fake.labels)
            if event == 'timeout':
                self.assertIn('Автоматически: Personal через 2 с', fake.labels)
                self.assertIn('Автоматически: Personal через 1 с', fake.labels)
            if event in ('Escape', 'close', 'manual-race'):
                self.assertTrue(fake.cancelled)

    def test_custom_timeout_and_invalid_options(self):
        fake = FakeTk('timeout')
        with patch.dict(sys.modules, tkinter=fake), \
             patch('formatter_modules.profile_selector.monotonic', side_effect=lambda: fake.now):
            self.assertEqual(select_profile(1), 'personal')
        self.assertIn('Автоматически: Personal через 1 с', fake.labels)
        for value in (0, -1, 61, True, 1.5, '3'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_profile(value)
