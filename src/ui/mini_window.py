import gettext

from gi.repository import Adw, Gtk, Gdk, GLib

from ..utility.file_dialogs import cancel_file_dialog
from ..utility.macos_window import float_mini_window
from ..utility.system import has_primary_modifier

_ = gettext.gettext


class MiniWindow(Adw.Window):
    """Floating, resizable chat window with a single, reversible owner."""

    def __init__(self, application, main_window, **kwargs):
        super().__init__(application=application, **kwargs)
        self.main_window = main_window
        self._restore_main = True
        self.set_title(_("Newelle Mini Window"))
        self.set_default_size(540, 520)
        self.set_size_request(360, 320)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label=_("Newelle")))
        expand = Gtk.Button(icon_name="view-restore-symbolic", tooltip_text=_("Open main window"))
        expand.connect("clicked", lambda *_: self.close())
        header.pack_end(expand)
        toolbar.add_top_bar(header)
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        toolbar.set_content(self.main_box)
        self.set_content(toolbar)

        self.chat_panel = main_window.secondary_message_chat_block
        self.original_parent = self.chat_panel.get_parent()
        main_window.close_transient_ui()
        self.original_parent.remove(self.chat_panel)
        self.main_box.append(self.chat_panel)
        main_window._apply_compact_input_bar(True)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key_pressed)
        self.add_controller(keys)
        self.connect("close-request", self._on_close_request)
        self.connect("map", self._on_map)
        self.connect("unmap", lambda *_: self.close_transient_ui())

    def _on_map(self, *_args):
        float_mini_window(self)
        GLib.idle_add(self.main_window.focus_input)

    def close_transient_ui(self):
        return self.main_window.close_transient_ui()

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            if not self.close_transient_ui():
                self.close()
            return True
        if has_primary_modifier(state) and Gdk.keyval_to_lower(keyval) == Gdk.KEY_w:
            self.close()
            return True
        return False

    def close_for_owner(self):
        """Return the panel during quit without reopening the main window."""
        self._restore_main = False
        self.close()

    def _on_close_request(self, *_args):
        if self.chat_panel is None:
            return False
        cancel_file_dialog(self)
        self.close_transient_ui()
        self.main_box.remove(self.chat_panel)
        self.original_parent.append(self.chat_panel)
        self.chat_panel = None
        app = self.get_application()
        if getattr(app, "mini_win", None) is self:
            app.mini_win = None
        self.main_window._refresh_compact_input_bar()
        if self._restore_main and not getattr(self.main_window, "_closing", False):
            # Complete the mini surface's close before mapping the restored
            # main surface; AppKit can still be delivering its last frame.
            GLib.idle_add(self._present_main, priority=GLib.PRIORITY_DEFAULT)
        return False

    def _present_main(self):
        if not getattr(self.main_window, "_closing", False):
            self.main_window.unminimize()
            self.main_window.present()
            self.main_window.focus_input()
        return GLib.SOURCE_REMOVE
