"""Exercise the packaged macOS UI without touching the user's settings or chats."""

import sys
import time
import traceback
from unittest.mock import patch


def run(version):
    import requests
    from gi.repository import Gio, GLib
    from newelle.main import create_application
    from newelle.controller import HandlersManager
    from newelle.utility.stdout_capture import StdoutMonitor

    errors = []
    original_hook = sys.excepthook

    def report_error(*exception):
        errors.append(exception)
        traceback.print_exception(*exception, file=sys.__stderr__)

    sys.excepthook = report_error
    app = create_application(version)
    app.set_application_id("io.github.qwersyk.Newelle.SmokeTest")
    app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
    app.settings.set_boolean("welcome-screen-shown", True)
    deadline = time.monotonic() + 45
    status = 1

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        print("PASS " + name, file=sys.__stdout__, flush=True)

    def check_window_controls(window, name):
        import objc
        from AppKit import NSWindowCloseButton
        from newelle.ui.widgets.browser_native_macos import _capsule_to_pointer, _get_native_window
        pointer = _capsule_to_pointer(window.get_surface().__gpointer__, None)
        native = objc.objc_object(c_void_p=_get_native_window(pointer))
        button = native.standardWindowButton_(NSWindowCloseButton)
        bounds = button.convertRect_toView_(button.bounds(), None)
        top = native.frame().size.height - bounds.origin.y - bounds.size.height
        check(0 <= top <= 64, name + " controls stay in the header")

    def stop():
        nonlocal status
        try:
            check(len(app.main_windows) == 2, "multiple main windows")
            check_window_controls(app.main_windows[0], "main window")
            check_window_controls(app.settingswindow, "settings window")
            app.settingswindow.close()
            check(all(getattr(w, "ui_built", False) for w in app.main_windows), "workspace window UI")
            for window in list(app.main_windows):
                window.close()
            check(not app.main_windows, "close all main windows")
            from newelle.window import MainWindow
            check(not any(isinstance(w, MainWindow) for w in app.get_windows()), "main windows released by GTK")
            check(not errors, "no unhandled UI exceptions")
            status = 0
        except Exception:
            traceback.print_exc(file=sys.__stderr__)
        finally:
            for window in app.get_windows():
                window.destroy()
            app.quit()
        return GLib.SOURCE_REMOVE

    def exercise():
        try:
            if time.monotonic() >= deadline:
                raise TimeoutError("Main window did not initialize")
            if app.win is None or not getattr(app.win, "ui_built", False):
                return GLib.SOURCE_CONTINUE
            check(True, "main window")
            app.new_chat_tab()
            check(app.win.chat_tabs.get_n_pages() == 2, "create chat tab")
            browser_tab = app.win.add_browser_tab(url="about:blank")
            check(browser_tab.get_child().native_browser is not None, "native WebKit browser")
            terminal_tab = app.win.add_terminal_tab(command="printf newelle-smoke; exit")
            check(terminal_tab is not None, "terminal tab")
            app.settings_action()
            check(app.settingswindow is not None, "settings with search and profiles")
            app.downloads_action()
            check(app.downloads_window is not None, "download manager")
            app.show_mini_window()
            app.mini_win.close()
            check(True, "mini window")
            from newelle.ui.voice_mode import VoiceModeWindow
            # Create and close the surface without opening the microphone.
            voice = VoiceModeWindow(application=app, main_window=app.win, on_closed=lambda *_: None)
            voice.present()
            GLib.timeout_add(150, lambda: voice.cancel() or GLib.SOURCE_REMOVE)
            check(True, "voice mode surface")
            app._smoke_voice = voice
            second = app.create_main_window(source=app.win, suppress_presentation=True)
            second.present()
            GLib.timeout_add(1500, stop)
        except Exception:
            traceback.print_exc(file=sys.__stderr__)
            errors.append(sys.exc_info())
            app.quit()
        return GLib.SOURCE_REMOVE

    def offline(*_args, **_kwargs):
        raise requests.ConnectionError("Network disabled during smoke test")

    try:
        with patch.object(requests.sessions.Session, "request", offline), \
             patch.object(HandlersManager, "cache_handlers", lambda manager: manager.handlers_cached.release()), \
             patch.object(HandlersManager, "install_missing_handlers"), \
             patch.object(StdoutMonitor, "start_monitoring"):
            GLib.timeout_add(100, exercise)
            app.run(["Newelle"])
    finally:
        sys.excepthook = original_hook
    return status
