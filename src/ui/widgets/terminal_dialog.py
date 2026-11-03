import gi
import os
import signal
from gettext import gettext as _
from gi.repository import Gtk, Adw, Gio, GLib, Pango, Gdk

from gi.repository.GObject import GObject
from .runtime import VTE_AVAILABLE
from ...utility.system import has_primary_modifier

if VTE_AVAILABLE:
    gi.require_version('Vte', '3.91')
    from gi.repository import Vte

if VTE_AVAILABLE:
    class Terminal(Vte.Terminal):
        def __init__(self, script: list):
            super().__init__(css_classes=["terminal"])
            self._detached = False
            self._spawn_done = False
            self.child_pid = None
            self.exit_code = None
            self.spawn_error = None
            self._spawn_cancel = Gio.Cancellable()
            self.set_font(Pango.FontDescription.from_string("Monospace 12"))
            self.set_clear_background(False)
            self.set_scrollback_lines(10000)
            pty = Vte.Pty.new_sync(Vte.PtyFlags.DEFAULT, None)
            self.set_pty(pty)
            self.connect("child-exited", self._on_child_exited)
            self.connect("unrealize", self._on_unrealize)
            pty.spawn_async(
                GLib.get_current_dir(), script, None, GLib.SpawnFlags.DEFAULT,
                None, None, -1, self._spawn_cancel, self._on_spawned, None,
            )
            keys = Gtk.EventControllerKey()
            keys.connect("key-pressed", self.on_key_press)
            self.add_controller(keys)

        @property
        def is_running(self):
            return not self._spawn_done or (self.child_pid is not None and self.exit_code is None)

        def _on_spawned(self, pty, result, *_args):
            self._spawn_done = True
            try:
                _success, pid = pty.spawn_finish(result)
            except GLib.Error as error:
                self.spawn_error = str(error)
                if not self._detached:
                    self.feed((self.spawn_error + "\r\n").encode("utf-8"))
                return
            self.child_pid = pid
            # Without watch_child VTE never reaps the shell or emits child-exited.
            self.watch_child(pid)
            if self._detached:
                self._terminate_child()

        def _on_child_exited(self, _terminal, status):
            self.exit_code = os.waitstatus_to_exitcode(status)

        def _on_unrealize(self, *_args):
            GLib.idle_add(self._detach_if_unrooted, priority=GLib.PRIORITY_DEFAULT)

        def _detach_if_unrooted(self):
            if self.get_root() is None:
                self.detach()
            return GLib.SOURCE_REMOVE

        def _terminate_child(self):
            if self.child_pid is not None and self.exit_code is None:
                try:
                    os.killpg(self.child_pid, signal.SIGHUP)
                except ProcessLookupError:
                    pass

        def detach(self):
            if not self._detached:
                self._detached = True
                self._spawn_cancel.cancel()
                self._terminate_child()

        def on_key_press(self, controller, keyval, keycode, state):
            if has_primary_modifier(state) and Gdk.keyval_to_lower(keyval) == Gdk.KEY_c:
                self.copy_clipboard()
                return True
            if has_primary_modifier(state) and Gdk.keyval_to_lower(keyval) == Gdk.KEY_v:
                self.paste_clipboard()
                return True
            return False

        def get_output(self):
            return self.get_text_format(Vte.Format.TEXT)

    class SessionTerminal(Vte.Terminal):
        """Interactive VTE view backed by an existing command session."""

        def __init__(self, session):
            super().__init__(css_classes=["terminal"])
            self.session = session
            self._detached = False
            self._last_size = None
            self.set_font(Pango.FontDescription.from_string("Monospace 12"))
            self.set_clear_background(False)
            self.set_scrollback_lines(10000)

            self.connect("commit", self._on_commit)
            key_controller = Gtk.EventControllerKey()
            key_controller.connect("key-pressed", self._on_key_press)
            self.add_controller(key_controller)

            self._listener_id, snapshot = self.session.subscribe_terminal_output(
                self._queue_output
            )
            if snapshot:
                self.feed(snapshot.encode("utf-8"))
            self._tick_callback_id = self.add_tick_callback(self._sync_size)

        def _queue_output(self, text):
            if not self._detached:
                GLib.idle_add(self._feed_output, text)

        def _feed_output(self, text):
            if self._detached:
                return False
            self.feed(text.encode("utf-8"))
            return False

        def _on_commit(self, _terminal, text, _size):
            if self._detached:
                return
            try:
                self.session.write_text(text)
            except Exception:
                self.detach()

        def _on_key_press(self, _controller, keyval, _keycode, state):
            ctrl = state & Gdk.ModifierType.CONTROL_MASK
            shift = state & Gdk.ModifierType.SHIFT_MASK
            shortcut = has_primary_modifier(state) or (ctrl and shift)
            if shortcut and Gdk.keyval_to_lower(keyval) == Gdk.KEY_c:
                self.copy_clipboard()
                return True
            if shortcut and Gdk.keyval_to_lower(keyval) == Gdk.KEY_v:
                self.paste_clipboard()
                return True
            return False

        def _sync_size(self, _widget, _frame_clock):
            if self._detached:
                return False
            size = (self.get_row_count(), self.get_column_count())
            if size != self._last_size:
                self._last_size = size
                try:
                    self.session.resize(*size)
                except Exception:
                    self.detach()
                    return False
            return True

        def detach(self):
            if self._detached:
                return
            self._detached = True
            self.session.unsubscribe_terminal_output(self._listener_id)
            if self._tick_callback_id is not None:
                self.remove_tick_callback(self._tick_callback_id)
                self._tick_callback_id = None

        def get_output(self):
            return self.get_text_format(Vte.Format.TEXT)
else:
    class Terminal(Gtk.Box):
        def __init__(self, script:list):
            super().__init__()
            self.append(Gtk.Label(label="Embedded terminal is not supported on this platform"))

        def get_output(self):
            return ""

    class SessionTerminal(Terminal):
        def __init__(self, _session):
            super().__init__([])

        def detach(self):
            pass

class TerminalDialog(Adw.Window):
    """A standalone, resizable terminal window.

    This intentionally is not an ``Adw.Dialog``: dialogs are presented inside
    the currently active window and cannot be resized like a desktop terminal.
    """

    def __init__(self, confirm_output=True, parent_window=None, **kwargs):
        super().__init__(**kwargs)

        self.set_title("Terminal")
        self.set_default_size(960, 640)
        self.set_resizable(True)
        self.set_modal(False)
        if parent_window is not None:
            self.set_transient_for(parent_window)

        self._confirm_output = confirm_output
        self._allow_close = not confirm_output
        self._terminal_detached = False
        self.connect("close-request", self._on_close_request)
        self.output_func = lambda x: x
        # Toolbar View
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_css_class("osd")
        toolbar_view.set_hexpand(True)
        toolbar_view.set_vexpand(True)

        # Header Bar
        header_bar = Adw.HeaderBar(
            show_start_title_buttons=False,
            show_end_title_buttons=False,
        )
        close_button = Gtk.Button(
            icon_name="window-close-symbolic",
            css_classes=["flat", "circular"],
            tooltip_text=_("Close"),
        )
        close_button.connect("clicked", lambda *_args: self.close())
        header_bar.pack_end(close_button)
        toolbar_view.add_top_bar(header_bar)

        # Scrolled Window
        self.terminal_scroller = Gtk.ScrolledWindow(
            hexpand=True,
            vexpand=True,
            propagate_natural_height=False,
            propagate_natural_width=False,
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )
        toolbar_view.set_content(self.terminal_scroller)
        self.set_content(toolbar_view)

    def load_terminal(self, command:list[str]):
        self.set_terminal(Terminal(command))

    def save_output_func(self, output_func):
        self.output_func = output_func

    def set_terminal(self, terminal):
        if hasattr(self, "terminal") and hasattr(self.terminal, "detach"):
            self.terminal.detach()
        self.terminal = terminal
        terminal.set_hexpand(True)
        terminal.set_vexpand(True)
        self.terminal_scroller.set_child(terminal)

    def load_session(self, session):
        self.set_terminal(SessionTerminal(session))

    def close_window(self,dialog, response):
        self._allow_close = True
        try:
            if response == "save":
                self.output_func(self.terminal.get_output())
            else:
                self.output_func(None)
        finally:
            self.close()

    def _on_close_request(self, *_args):
        if self._allow_close:
            self._detach_terminal()
            return False

        dialog = Adw.AlertDialog(
            body=_(
                "Do you want to send the output of the terminal to the LLM "
                "to get a response?\nNote: Only the visible text will be sent "
                "as response"
            ),
            title=_("Send output?"),
        )
        dialog.add_response("save", _("Send output"))
        dialog.add_response("close", _("Discard output"))
        dialog.set_response_appearance("close", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.close_window)
        dialog.present(self)
        return True

    def _detach_terminal(self):
        if self._terminal_detached:
            return
        self._terminal_detached = True
        if hasattr(self, "terminal") and hasattr(self.terminal, "detach"):
            self.terminal.detach()
