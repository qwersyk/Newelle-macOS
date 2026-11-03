"""Exercise the packaged macOS UI without touching the user's settings or chats."""

import sys
import os
from pathlib import Path
import threading
import faulthandler
import time
import traceback
from unittest.mock import patch


def run(version):
    # Independent of GLib: a blocked native event loop must produce a useful
    # stack trace and a failing exit rather than hanging the runner indefinitely.
    faulthandler.dump_traceback_later(150, exit=True, file=sys.__stderr__)
    import requests
    from AppKit import NSApplication, NSOpenPanel, NSWindowCloseButton
    from gi.repository import Gio, GLib, Gtk
    from newelle.main import create_application
    from newelle.controller import HandlersManager
    from newelle.utility.file_dialogs import show_file_dialog
    from newelle.utility.macos_window import native_window
    from newelle.utility.stdout_capture import StdoutMonitor
    from newelle.utility.system import activate_macos_application

    errors = []
    for variable, getter in (("XDG_CONFIG_HOME", GLib.get_user_config_dir),
                             ("XDG_DATA_HOME", GLib.get_user_data_dir),
                             ("XDG_CACHE_HOME", GLib.get_user_cache_dir)):
        if Path(getter()).resolve() != Path(os.environ[variable]).resolve():
            raise RuntimeError("Smoke test directory is not isolated: " + variable)
    original_hook = sys.excepthook
    original_thread_hook = threading.excepthook

    def report_error(*exception):
        errors.append(exception)
        traceback.print_exception(*exception, file=sys.__stderr__)

    sys.excepthook = report_error
    threading.excepthook = lambda args: report_error(args.exc_type, args.exc_value, args.exc_traceback)
    app = create_application(version)
    app.set_application_id("io.github.qwersyk.Newelle.SmokeTest")
    app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
    app.settings.set_boolean("welcome-screen-shown", True)
    deadline = time.monotonic() + 110
    completed = False

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        print("PASS " + name, file=sys.__stdout__, flush=True)

    def check_window_controls(window, name):
        native = native_window(window)
        button = native.standardWindowButton_(NSWindowCloseButton)
        bounds = button.convertRect_toView_(button.bounds(), None)
        top = native.frame().size.height - bounds.origin.y - bounds.size.height
        check(0 <= top <= 64, name + " controls stay in the header")
        check(native.isOpaque() and native.backgroundColor().alphaComponent() == 1.0,
              name + " has an opaque native background")
        check(native.preservesContentDuringLiveResize(), name + " preserves contents while resizing")

    def cancel_result(dialog, result):
        try:
            dialog.open_finish(result)
        except GLib.Error:
            pass
        panel_results.append(True)

    panel_results = []

    def panels():
        return [w for w in NSApplication.sharedApplication().windows() if isinstance(w, NSOpenPanel)]

    def exercise():
        nonlocal completed
        while app.win is None or not getattr(app.win, "ui_built", False):
            yield 100
        main = app.win
        if "--mini" in sys.argv:
            while app.mini_win is None or not app.mini_win.get_mapped():
                yield 50
            check(not main.get_visible(), "cold startup opens only mini window")
            app._present_main_window()
            yield 250
            check(app.mini_win is None and main.get_mapped(), "cold mini returns to main")
        check(True, "main window")
        app.new_chat_tab()
        check(main.chat_tabs.get_n_pages() == 2, "create chat tab")
        browser_tab = main.add_browser_tab(url="about:blank")
        check(browser_tab.get_child().native_browser is not None, "native WebKit browser")

        # Verify the child actually ran and exited, rather than just constructing
        # a VTE widget (the old check missed a fork/pre-exec crash).
        for index in range(3):
            marker = "newelle-smoke-" + str(index)
            page = main.add_terminal_tab(command="printf " + marker + "; exit")
            terminal = page.get_child().get_first_child()
            while terminal.is_running:
                yield 50
            yield 1000
            check(terminal.exit_code == 0 and marker in terminal.get_output(), "terminal output and clean exit " + str(index))
            main.canvas_tabs.close_page(page)
        page = main.add_terminal_tab(command="printf ready; read reply; printf received:$reply; exit")
        terminal = page.get_child().get_first_child()
        while "ready" not in terminal.get_output():
            yield 50
        terminal.feed_child(b"hello\n")
        while terminal.is_running:
            yield 50
        yield 100
        check("received:hello" in terminal.get_output(), "interactive terminal input")
        main.canvas_tabs.close_page(page)
        page = main.add_terminal_tab()
        terminal = page.get_child().get_first_child()
        yield 100
        main.canvas_tabs.close_page(page)
        while terminal.is_running:
            yield 50
        check(True, "closing terminal tab releases shell")

        popover = main.get_active_chat_tab().quick_toggles_popover
        popover.popup()
        yield 250
        popup_native = native_window(popover)
        check(popup_native is not None and popup_native.isVisible(), "popover opens")
        main.close_transient_ui()
        yield 250
        activate_macos_application()
        yield 100
        check(not popover.get_visible() and not popup_native.isVisible(), "activation leaves dismissed popover hidden")

        chooser = Gtk.FileDialog(title="Newelle smoke file panel", modal=True)
        request = show_file_dialog(chooser, "open", main, cancel_result)
        yield 350
        native_panels = panels()
        request.cancel()
        while not panel_results:
            yield 50
        yield 150
        activate_macos_application()
        check(not any(w.isVisible() for w in native_panels), "cancelled file panel stays hidden on activation")

        panel = main.secondary_message_chat_block
        parent = panel.get_parent()
        for index in range(3):
            app.show_mini_window()
            mini = app.mini_win
            yield 450
            check(mini.get_mapped() and not main.get_visible(), "mini window hides main " + str(index))
            check(mini.get_resizable() and panel.get_root() is mini, "mini window owns chat " + str(index))
            check_window_controls(mini, "mini window")
            app.show_mini_window()
            check(app.mini_win is mini, "mini window reused " + str(index))
            if index == 1:
                show_file_dialog(Gtk.FileDialog(title="Mini smoke file panel", modal=True), "open", main, cancel_result)
                yield 250
                check(getattr(mini, "_newelle_file_dialog", None) is not None, "mini window owns native file panel")
            if index == 2:
                app._present_main_window()
            else:
                mini.close()
            yield 450
            check(app.mini_win is None and main.get_visible() and panel.get_parent() is parent, "mini window restores chat " + str(index))
        while len(panel_results) < 2:
            yield 50
        check(not any(w.isVisible() for w in panels()), "closing mini cancels owned file panel")

        app.settings_action()
        app.downloads_action()
        check(app.settingswindow is not None, "settings with search and profiles")
        check(app.downloads_window is not None, "download manager")
        check(app.settingswindow.get_application() is app and app.downloads_window.get_application() is app,
              "utility windows belong to the application")
        from newelle.ui.voice_mode import VoiceModeWindow
        voice = VoiceModeWindow(application=app, main_window=main, on_closed=lambda *_: None)
        voice.present()
        yield 150
        voice.cancel()
        check(True, "voice mode surface")
        second = app.create_main_window(source=main, suppress_presentation=True)
        second.present()
        while not getattr(second, "ui_built", False):
            yield 100
        yield 250
        check(len(app.main_windows) == 2, "multiple main windows")
        check_window_controls(main, "main window")
        check_window_controls(app.settingswindow, "settings window")
        second.close()
        check(len(app.main_windows) == 1, "closing secondary window keeps primary")
        # Quit from mini mode with preferences and downloads still open.
        app.show_mini_window()
        yield 150
        if "--direct-quit" in sys.argv:
            app.quit()
        else:
            app.quit_application()
            check(not app.main_windows, "quit from mini releases main window")
            check(app.mini_win is None, "quit releases mini without reopening main")
        check(not errors, "no unhandled UI exceptions")
        completed = True
        # Let the application exit on its own. Utility windows must not keep it alive.

    steps = exercise()

    def close_during_startup(*_args):
        nonlocal completed
        check(app.win is not None and not getattr(app.win, "ui_built", False), "close requested during startup")
        app.win.close()
        completed = True

    def advance():
        try:
            if time.monotonic() >= deadline:
                raise TimeoutError("UI smoke test exceeded 110 seconds")
            delay = next(steps)
            GLib.timeout_add(delay, advance)
        except StopIteration:
            pass
        except Exception:
            errors.append(sys.exc_info())
            traceback.print_exc(file=sys.__stderr__)
            app.quit()
        return GLib.SOURCE_REMOVE

    def timeout():
        errors.append((TimeoutError, TimeoutError("Application did not quit"), None))
        print("FAIL application did not quit", file=sys.__stderr__, flush=True)
        app.quit()
        return GLib.SOURCE_REMOVE

    def offline(*_args, **_kwargs):
        raise requests.ConnectionError("Network disabled during smoke test")

    try:
        with patch.object(requests.sessions.Session, "request", offline), \
             patch.object(HandlersManager, "cache_handlers", lambda manager: manager.handlers_cached.release()), \
             patch.object(HandlersManager, "install_missing_handlers"), \
             patch.object(StdoutMonitor, "start_monitoring"):
            if "--close-during-startup" in sys.argv:
                app.connect("activate", close_during_startup)
            else:
                GLib.timeout_add(100, advance)
            GLib.timeout_add_seconds(115, timeout)
            app.run(["Newelle"] + (["--mini"] if "--mini" in sys.argv else []))
        check(completed and not errors, "all lifecycle checks completed")
        check(not app.main_windows and app.mini_win is None, "main and mini owners released on shutdown")
        check(not app.get_windows(), "all application windows released on quit")
        toplevels = Gtk.Window.get_toplevels()
        check(not any(toplevels.get_item(index).get_visible() for index in range(toplevels.get_n_items())),
              "no unregistered visible windows left behind")
        return 0
    except Exception:
        traceback.print_exc(file=sys.__stderr__)
        return 1
    finally:
        for window in list(app.get_windows()):
            window.destroy()
        sys.excepthook = original_hook
        threading.excepthook = original_thread_hook
        faulthandler.cancel_dump_traceback_later()
