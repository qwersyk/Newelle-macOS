import gettext

from gi.repository import Gtk, Gdk

from ..utility.system import has_primary_modifier

_ = gettext.gettext


class MiniWindow(Gtk.Window):
    """Compact window that temporarily hosts the main chat panel."""

    def __init__(self, application, main_window, **kwargs):
        super().__init__(application=application, **kwargs)
        self.main_window = main_window
        self.set_title(_("Newelle Mini Window"))
        self.set_default_size(540, 520)
        self.set_decorated(False)
        self.set_resizable(False)
        self.add_css_class("mini-window")

        # WindowHandle so the undecorated window can be dragged around
        self.handle = Gtk.WindowHandle()
        self.set_child(self.handle)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.handle.set_child(self.main_box)

        # Shown in the main window while the chat panel is hosted here
        self.placeholder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.placeholder.set_valign(Gtk.Align.CENTER)
        self.placeholder.set_halign(Gtk.Align.CENTER)
        self.placeholder.set_vexpand(True)
        placeholder_label = Gtk.Label(label=_("Chat is opened in mini window"))
        placeholder_label.add_css_class("dim-label")
        self.placeholder.append(placeholder_label)

        self.chat_panel = None
        self.original_parent = None
        self._attach_chat_panel()

        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)
        self.connect('close-request', self._on_close_request)

    def _attach_chat_panel(self):
        self.chat_panel = self.main_window.secondary_message_chat_block
        parent = self.chat_panel.get_parent()
        if parent is not None:
            self.original_parent = parent
            self.chat_panel.unparent()
            self.original_parent.append(self.placeholder)
        self.main_box.append(self.chat_panel)
        # The mini window always uses the compact input bar, whatever the setting
        self.main_window._apply_compact_input_bar(True)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if has_primary_modifier(state) and Gdk.keyval_to_lower(keyval) == Gdk.KEY_w:
            self.close()
            return True
        return False
    def _on_close_request(self, *args):
        if self.chat_panel is not None:
            if self.chat_panel.get_parent() is not None:
                self.chat_panel.unparent()

            if self.placeholder.get_parent() is not None:
                self.placeholder.unparent()

            if self.original_parent is not None:
                self.original_parent.append(self.chat_panel)

            self.chat_panel = None
            self.original_parent = None
            # Give each tab back the layout chosen in the settings
            self.main_window._refresh_compact_input_bar()

        return False
