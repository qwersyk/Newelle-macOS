import sys
import os
import signal
from gettext import gettext as _
import threading
import gi

from .utility.util import convert_history_openai

gi.require_version('Gtk', '4.0')
gi.require_version('GtkSource', '5')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, Gdk, GLib
from .ui_controller import HeadlessController 
from .ui.settings import Settings
from .window import MainWindow
from .ui.mini_window import MiniWindow
from .ui.shortcuts import Shortcuts
from .ui.thread_editing import ThreadEditing
from .ui.scheduled_tasks import ScheduledTasksWindow
from .utility.system import activate_macos_application, primary_accel
from .ui.downloads import DownloadsWindow
from .ui.voice_mode import VoiceModeWindow


def requested_launch_mode(options):
    """Resolve per-invocation window flags with Voice Mode taking priority."""
    if options.contains("voice"):
        return "voice"
    if options.contains("mini"):
        return "mini"
    return None


class MyApp(Adw.Application):
    def __init__(self, version, **kwargs):
        self.version = version
        super().__init__(flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE, **kwargs)
        self.settings = Gio.Settings.new("io.github.qwersyk.Newelle")
        self.settingswindow = None
        self.mini_win = None
        self.main_windows = []
        self.add_main_option("run-action", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING, "Run an action", "ACTION")
        self.add_main_option("mini", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Start in mini window mode", None)
        self.add_main_option("voice", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Start one-shot Voice Mode", None)
        css = '''
        .code{
        background-color: rgb(38,38,38);
        }

        .code .sourceview text{
            background-color: rgb(38,38,38);
        }
        .code .sourceview border gutter{
            background-color: rgb(38,38,38);
        }
        .sourceview{
            color: rgb(192,191,188);
        }
        .copy-action{
            color:rgb(255,255,255);
            background-color: rgb(38,162,105);
        }
        /* Named newelle-icon-large: libadwaita's AdwClamp applies its own
        `.large` class to preferences-page content on wide windows, and
        -gtk-icon-size is inherited, which would blow up every icon there. */
        .newelle-icon-large{
            -gtk-icon-size:100px;
        }
        .empty-folder{
            font-size:25px;
            font-weight:800;
            -gtk-icon-size:120px;
        }
        /* Chat message bubbles */
        .bubble{
            padding: 10px 14px;
        }
        /* User: right side, accent tint (no avatar -> color identifies sender) */
        .user{
            background-color: alpha(@accent_bg_color, 0.16);
            border-radius: 16px 16px 4px 16px;
        }
        .file{
            background-color: alpha(@accent_bg_color, 0.12);
            border-radius: 16px 16px 4px 16px;
        }
        .folder{
            background-color: alpha(@accent_bg_color, 0.12);
            border-radius: 16px 16px 4px 16px;
        }
        /* Assistant: left side, soft neutral */
        .assistant{
            background-color: alpha(@window_fg_color, 0.07);
            border-radius: 16px 16px 16px 4px;
        }
        .done{
            background-color: alpha(@success_bg_color, 0.16);
            border-radius: 16px 16px 16px 4px;
        }
        .failed{
            background-color: alpha(@error_bg_color, 0.16);
            border-radius: 16px 16px 16px 4px;
        }
        /* Centered system messages: symmetric radius */
        .message-warning{
            background-color: alpha(@warning_bg_color, 0.16);
            border-radius: 16px;
        }
        /* Assistant sender name (shown above the bubble) */
        .bubble-sender{
            font-weight: 700;
            color: @accent_color;
        }
        /* Floating message action toolbar (appears on hover) */
        .message-actions{
            background-color: alpha(@window_bg_color, 0.9);
            border-radius: 999px;
            padding: 2px 4px;
        }
        /* Context compaction divider in the chat history */
        .compaction-line.start{
            background-image: linear-gradient(to right, alpha(@accent_color, 0), alpha(@accent_color, 0.45));
        }
        .compaction-line.end{
            background-image: linear-gradient(to left, alpha(@accent_color, 0), alpha(@accent_color, 0.45));
        }
        .compaction-pill{
            min-height: 0;
            padding: 4px 12px;
            border-radius: 999px;
            background-color: alpha(@accent_bg_color, 0.14);
            box-shadow: inset 0 0 0 1px alpha(@accent_color, 0.25);
            color: @accent_color;
            font-weight: 600;
            font-size: 0.9em;
        }
        .compaction-pill:hover{
            background-color: alpha(@accent_bg_color, 0.22);
        }
        .compaction-summary{
            padding: 12px 14px;
            border-radius: 12px;
            background-color: alpha(@accent_bg_color, 0.06);
            box-shadow: inset 0 0 0 1px alpha(@accent_color, 0.15);
        }
        .transparent{
            background-color: rgba(0,0,0,0);
        }
        .chart{
            background-color: rgba(61, 152, 255,0.25);
        }
        .right-angles{
            border-radius: 0;
        }
        .image{
            -gtk-icon-size:400px;
        }
        .video {
            min-height: 400px;
        }
        .mini-window {
            border-radius: 12px;
            border: 1px solid alpha(@card_fg_color, 0.15);
            box-shadow: 0 2px 4px alpha(black, 0.1);
            margin: 4px;
        }
        @keyframes pulse_opacity {
          0% { opacity: 1.0; }
          50% { opacity: 0.5; }
          100% { opacity: 1.0; }
        }

        .pulsing-label {
          animation-name: pulse_opacity;
          animation-duration: 1.8s;
          animation-timing-function: ease-in-out;
          animation-iteration-count: infinite;
        }

        /* Workspace controls follow the current light/dark Adwaita palette. */
        .workspace-switcher > button {
          padding: 10px 12px;
          border-radius: 12px;
          background-color: alpha(@view_fg_color, 0.045);
          box-shadow: inset 0 0 0 1px alpha(@view_fg_color, 0.06);
        }
        .workspace-switcher > button:hover,
        .workspace-switcher > button:checked {
          background-color: alpha(@accent_bg_color, 0.12);
        }
        .workspace-popover row.workspace-active {
          background-color: alpha(@accent_bg_color, 0.10);
        }
        .workspace-popover row.workspace-active:hover {
          background-color: alpha(@accent_bg_color, 0.17);
        }

        .workspace-avatar-button > button {
          padding: 6px;
          border-radius: 999px;
        }
        .workspace-avatar-badge {
          padding: 5px;
          border: 2px solid @window_bg_color;
          border-radius: 999px;
          background-color: @accent_bg_color;
          color: @accent_fg_color;
        }

        /* Chat history row styling */
        .navigation-sidebar row.chat-row-selected {
          background-color: alpha(@accent_bg_color, 0.15);
          border-radius: 6px;
        }
        
        .navigation-sidebar row.chat-row-selected:hover {
          background-color: alpha(@accent_bg_color, 0.25);
        }

        .window-bar-label {
                color: @view_fg_color;
                font-weight: 600;
        }
        @keyframes chat_locked_pulse {
            0% { background-color: alpha(@view_fg_color, 0.06); }
            50% { background-color: alpha(@view_fg_color, 0.12); }
            100% { background-color: alpha(@view_fg_color, 0.06); }
        }
        .chat-locked {
                background-color: alpha(@view_fg_color, 0.06);
                animation: chat_locked_pulse 1.6s ease-in-out infinite;
        }

        /* Folder row styling */
        .navigation-sidebar row.folder-row {
          border-radius: 6px;
          margin-top: 2px;
        }

        .navigation-sidebar row.folder-row-drop-hover {
          background-color: alpha(@accent_bg_color, 0.20);
          border-radius: 6px;
        }

        .folder-icon-picker-btn {
          min-width: 36px;
          min-height: 36px;
          padding: 4px;
        }

        .folder-icon-picker-btn:checked {
          background-color: alpha(@accent_bg_color, 0.25);
        }

        .mode-icon-picker-btn {
          min-width: 36px;
          min-height: 36px;
          padding: 4px;
        }

        .mode-icon-picker-btn:checked {
          background-color: alpha(@accent_bg_color, 0.25);
        }

        .unfolder-drop-area {
          border-radius: 6px;
        }

        .unfolder-drop-area-hover {
          background-color: alpha(@accent_bg_color, 0.12);
        }

        .message-text {
          line-height: 1.75;
        }

        .source-chip {
          min-height: 22px;
          padding: 1px 7px;
          margin: 0 2px;
          color: @accent_color;
          background-color: alpha(@accent_bg_color, 0.14);
        }

        .source-chip:hover {
          background-color: alpha(@accent_bg_color, 0.24);
        }

        .sources-button {
          color: @accent_color;
          background-color: alpha(@accent_bg_color, 0.14);
          border-radius: 999px;
        }

        .sources-button:hover,
        .sources-button:checked {
          background-color: alpha(@accent_bg_color, 0.24);
        }

        .source-chip label {
          font-size: 0.95em;
          font-weight: 600;
        }

        .prompt-drop-target {
          outline: 2px solid @accent_color;
          outline-offset: -2px;
          border-radius: 12px;
        }
        '''
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(css, -1)
        display = Gdk.Display.get_default() 
        if display is not None:
            icon_dir = os.getenv("NEWELLE_ICON_DIR")
            if icon_dir and os.path.isdir(icon_dir):
                Gtk.IconTheme.get_for_display(display).add_search_path(icon_dir)
            Gtk.StyleContext.add_provider_for_display(
                display,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        self.connect('activate', self.on_activate)
        action = Gio.SimpleAction.new("about", None)
        action.connect('activate', self.on_about_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("shortcuts", None)
        action.connect('activate', self.on_shortcuts_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("preferences", None)
        action.connect('activate', self.settings_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("settings", None)
        action.connect('activate', self.settings_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("thread_editing", None)
        action.connect('activate', self.thread_editing_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("scheduled_tasks", None)
        action.connect('activate', self.scheduled_tasks_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("downloads", None)
        action.connect('activate', self.downloads_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("extension", None)
        action.connect('activate', self.extension_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("interfaces", None)
        action.connect('activate', self.interfaces_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("export_current_chat", None)
        action.connect('activate', self.export_current_chat_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("export_all_chats", None)
        action.connect('activate', self.export_all_chats_action)
        self.add_action(action)
        action = Gio.SimpleAction.new("import_chats", None)
        action.connect('activate', self.import_chats_action)
        self.add_action(action)

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.build_menubar()

    def create_action(self, name, callback, shortcuts=None):
        action = self.lookup_action(name)
        if action is None:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        if shortcuts:
            self.set_action_shortcuts(name, shortcuts)

    def set_action_shortcuts(self, name, shortcuts):
        self.set_accels_for_action(f"app.{name}", shortcuts)

    def build_menubar(self):
        menubar = Gio.Menu()

        file_menu = Gio.Menu()
        file_menu.append(_("New Chat"), "app.new_chat")
        file_menu.append(_("New Tab"), "app.new_chat_tab")
        file_menu.append(_("Mini Window"), "app.open_mini_window")
        file_menu.append(_("Close Window"), "app.close_active_window")
        menubar.append_submenu(_("File"), file_menu)

        view_menu = Gio.Menu()
        view_menu.append(_("Explorer Tab"), "app.new_explorer_tab")
        view_menu.append(_("Terminal Tab"), "app.new_terminal_tab")
        view_menu.append(_("Browser Tab"), "app.new_browser_tab")
        menubar.append_submenu(_("View"), view_menu)

        chat_menu = Gio.Menu()
        chat_menu.append(_("Reload Chat"), "app.reload_chat")
        chat_menu.append(_("Reload Folder"), "app.reload_folder")
        chat_menu.append(_("Export Current Chat"), "app.export_current_chat")
        chat_menu.append(_("Export All Chats"), "app.export_all_chats")
        chat_menu.append(_("Import Chats"), "app.import_chats")
        menubar.append_submenu(_("Chat"), chat_menu)

        tools_menu = Gio.Menu()
        tools_menu.append(_("Keyboard shortcuts"), "app.shortcuts")
        tools_menu.append(_("Thread Editing"), "app.thread_editing")
        tools_menu.append(_("Scheduled Tasks"), "app.scheduled_tasks")
        tools_menu.append(_("Downloads"), "app.downloads")
        tools_menu.append(_("Voice Mode"), "app.voice_mode")
        tools_menu.append(_("Extensions"), "app.extension")
        tools_menu.append(_("Interfaces"), "app.interfaces")
        menubar.append_submenu(_("Tools"), tools_menu)

        self.set_menubar(menubar)

    def _has_visible_windows(self) -> bool:
        return any(window.get_mapped() for window in self.get_windows())

    def _ensure_main_window(self) -> MainWindow:
        if self.win is None:
            self.create_main_window()
        return self.win

    def _present_main_window(self) -> MainWindow:
        window = self._ensure_main_window()
        if getattr(window, "mini_mode", False):
            window.leave_mini_mode()
        window.present()
        if hasattr(window, "stabilize_initial_layout"):
            GLib.idle_add(window.stabilize_initial_layout)
        GLib.idle_add(activate_macos_application)
        GLib.timeout_add(100, lambda: activate_macos_application() or False)
        return window

    @property
    def win(self):
        """Application actions follow the main window owning the active surface."""
        active = self.get_active_window()
        while active is not None:
            if active in self.main_windows:
                return active
            owner = getattr(active, "main_window", None)
            if owner in self.main_windows:
                return owner
            active = active.get_transient_for()
        return getattr(self, "_last_main_window", None)

    def _main_window_focused(self, window, _property):
        if window.is_active():
            self._last_main_window = window
            from .utility.replacehelper import ReplaceHelper
            ReplaceHelper.set_controller(window.controller)

    def create_main_window(self, workspace_id=None, source=None, suppress_presentation=False):
        window = MainWindow(
            application=self, workspace_id=workspace_id,
            shared_controller=source.controller if source else None,
            suppress_presentation=suppress_presentation,
        )
        self.main_windows.append(window)
        self._last_main_window = window
        window.connect("notify::is-active", self._main_window_focused)
        window.connect("close-request", self.close_window)
        window.connect("destroy", self._main_window_destroyed)
        return window

    def _main_window_destroyed(self, window):
        if window in self.main_windows:
            self.main_windows.remove(window)
        if getattr(self, "_last_main_window", None) is window:
            self._last_main_window = self.main_windows[-1] if self.main_windows else None

    def workspace_window(self, workspace_id, exclude=None):
        return next((window for window in self.main_windows
                     if window is not exclude and window.controller.active_workspace_id == workspace_id), None)

    def open_workspace_window(self, workspace_id, source):
        if workspace_id not in source.controller.workspaces:
            source.workspace_toast(_("Workspace not found."))
            return
        existing = self.workspace_window(workspace_id)
        if existing is not None:
            existing.present()
            return
        # A cached tab can still own a response. Leave its UI with its controller
        # until that response finishes; other workspaces can open immediately.
        for window in self.main_windows:
            if not window.release_workspace_tabs(workspace_id):
                source.workspace_toast(_("Finish or stop active work before opening this workspace in another window."))
                return
        source.save_workspace_tabs()
        window = self.create_main_window(workspace_id, source, suppress_presentation=True)
        window.present()

    def on_shortcuts_action(self, *a):
        shortcuts = Shortcuts(self)
        shortcuts.present()

    def on_about_action(self, *a):
        Adw.AboutWindow(transient_for=self.props.active_window,
                        application_name='Newelle',
                        application_icon='io.github.qwersyk.Newelle',
                        developer_name='qwersyk',
                        version=self.version,
                        issue_url='https://github.com/qwersyk/Newelle/issues',
                        website='https://github.com/qwersyk/Newelle',
                        developers=['Yehor Hliebov  https://github.com/qwersyk',"Francesco Caracciolo https://github.com/FrancescoCaracciolo", "Pim Snel https://github.com/mipmip"],
                        documenters=["Francesco Caracciolo https://github.com/FrancescoCaracciolo"],
                        designers=["Nokse22 https://github.com/Nokse22", "Jared Tweed https://github.com/JaredTweed"],
                        translator_credits="\n".join(["Amine Saoud (Arabic) https://github.com/amiensa","Heimen Stoffels (Dutch) https://github.com/Vistaus","Albano Battistella (Italian) https://github.com/albanobattistella","Oliver Tzeng (Traditional Chinese, all languages) https://github.com/olivertzeng","Aritra Saha (Bengali, Hindi) https://github.com/olumolu","NorwayFun (Georgian) https://github.com/NorwayFun"]),
                        copyright='© 2025 qwersyk').present()

    def thread_editing_action(self, *a):
        threadediting = ThreadEditing(self)
        threadediting.present()

    def scheduled_tasks_action(self, *a):
        scheduled_tasks = ScheduledTasksWindow(self)
        scheduled_tasks.present()

    def downloads_action(self, *a):
        window = getattr(self, "downloads_window", None)
        if window is None:
            window = DownloadsWindow(self)
            window.connect("close-request", self._downloads_window_closed)
            self.downloads_window = window
        window.present()

    def _downloads_window_closed(self, *_args):
        self.downloads_window = None
        return False

    def settings_action(self, *a): 
        if self.settingswindow is not None and self.settingswindow.get_visible():
            self.settingswindow.present()
            return
        settings = Settings(self, self._present_main_window().controller)
        settings.present()
        settings.connect("close-request", self.close_settings)
        self.settingswindow = settings

    def settings_action_paged(self, page=None, *a): 
        if self.settingswindow is not None and self.settingswindow.get_visible():
            self.settingswindow.present()
            return
        settings = Settings(self, self._present_main_window().controller, False, page)
        settings.present()
        settings.connect("close-request", self.close_settings)
        self.settingswindow = settings
    
    def close_settings(self, *a):
        settings_window = a[0]
        window = settings_window.controller.ui_controller.window
        window.settings.set_int("chat", window.chat_id)
        window.save_workspace_tabs()
        window.update_settings()
        settings_window.destroy()
        if self.settingswindow is settings_window:
            self.settingswindow = None
        return True

    def extension_action(self, *a):
        self.settings_action_paged("Extensions")

    def interfaces_action(self, *a):
        self.settings_action_paged("Interfaces")
    
    def export_current_chat_action(self, *a):
        """Export the current chat"""
        if self.win is not None:
            self.win.export_chat(export_all=False)
    
    def export_all_chats_action(self, *a):
        """Export all chats"""
        if self.win is not None:
            self.win.export_chat(export_all=True)
    
    def import_chats_action(self, *a):
        """Import chats from a file"""
        if self.win is not None:
            self.win.import_chat(None)
    
    def stdout_monitor_action(self, *a):
        """Show the stdout monitor dialog"""
        self.win.show_stdout_monitor_dialog()
    
    def close_window(self, window, *a):
        if not getattr(window, "ui_built", False):
            # UI construction is queued on the main loop. Do not destroy a
            # window while that callback is still waiting to initialize it.
            return True
        if getattr(self, "mini_win", None) is not None and self.mini_win.main_window is window and self.mini_win.get_visible():
            self.mini_win.close()
        if getattr(self, "voice_win", None) is not None and (self.voice_win.main_window is window or self.voice_win.controller is window.controller):
            self.voice_win.cancel()
        window.close_transient_ui()
        window.save_main_window_geometry(mapped_only=True)
        window.save_workspace_tabs()
        window.remember_workspace_drafts()
        if len(self.main_windows) > 1:
            self._close_main_window(window)
            return False
        from .utility.command_runner import get_command_execution_manager
        from .utility.command_sessions import get_command_session_manager
        from .utility.download_manager import get_download_manager

        legacy_running = any(
            element.poll() is None for element in window.streams
        )
        command_running = bool(get_command_execution_manager().list_all())
        session_running = bool(get_command_session_manager().list_all())
        downloads_running = get_download_manager().list(active=True)
        if not legacy_running and not command_running and not session_running and not downloads_running:
            self._close_main_window(window)
            return False
        else:
            if downloads_running:
                heading = _("Downloads or installations are still running")
                body = _(
                    "Closing Newelle can leave non-cancellable installations "
                    "incomplete. Cancellable downloads will be asked to stop."
                )
            else:
                heading = _("Terminal commands are still running in the background")
                body = _("When you close the window, they will be automatically terminated")
            dialog = Adw.MessageDialog(
                transient_for=window,
                heading=heading,
                body=body,
                body_use_markup=True,
            )
            dialog.add_response("cancel", _("Cancel"))
            dialog.add_response("close", _("Close"))
            dialog.set_response_appearance("close", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")
            dialog.connect("response", self.close_message, window)
            dialog.present()
            return True
    
    def _close_main_window(self, window):
        window.close_transient_ui()
        window.save_main_window_geometry(mapped_only=True)
        window.save_workspace_tabs()
        window.remember_workspace_drafts()
        for view in (window.chat_tabs, *window._workspace_views.values()):
            for index in range(view.get_n_pages()):
                tab = view.get_nth_page(index).get_child()
                if not tab.status:
                    tab.stop_chat()
        for process in window.streams:
            if process.poll() is None:
                process.terminate()
        from .utility.command_runner import get_command_execution_manager
        from .utility.command_sessions import get_command_session_manager
        chat_ids = set(window.controller.workspace_chats())
        for view in window._workspace_views.values():
            chat_ids.update(view.get_nth_page(index).get_child().chat_id for index in range(view.get_n_pages()))
        scope = id(window.controller.workspace_storage)
        owners = {("chat", scope, str(chat_id)) for chat_id in chat_ids}
        for execution in get_command_execution_manager().list_all():
            if execution.owner in owners:
                execution.cancel()
        sessions = get_command_session_manager()
        for session in sessions.list_all():
            if session.owner in owners:
                sessions.forget(session)
                threading.Thread(target=session.terminate, daemon=True).start()
        self.settings.set_int("chat", window.chat_id)
        self.settings.set_string("current-profile", window.settings.get_string("current-profile"))
        window.controller.save_chats()
        window.controller.close_application()
        self._main_window_destroyed(window)

    def close_message(self,a,status,window):
        if status=="close":
            for i in window.streams:
                if i.poll() is None:
                    i.terminate()
            from .utility.command_runner import shutdown_command_executions
            from .utility.command_sessions import shutdown_command_sessions
            from .utility.download_manager import get_download_manager
            if len(self.main_windows) == 1:
                for task in get_download_manager().list(active=True):
                    if task.cancellable:
                        get_download_manager().cancel(task.task_id)
                shutdown_command_executions()
                shutdown_command_sessions()
            self._close_main_window(window)
            window.destroy()

    def do_command_line(self, command_line):
        options = command_line.get_options_dict()
        launch_mode = requested_launch_mode(options)
        if launch_mode == "voice":
            self.start_in_voice = True
            self.start_in_mini = False
        elif launch_mode == "mini":
            self.start_in_mini = True
        if options.contains("run-action"):
            action_name = options.lookup_value("run-action").get_string()
            if self.lookup_action(action_name):
                self.activate_action(action_name, None)
            else:
                command_line.printerr(f"Action '{action_name}' not found.\n")
                return 1

        self.activate()
        return 0

    def on_activate(self, app):
        voice_requested = getattr(self, "start_in_voice", False)
        if self.win is None:
            self.create_main_window(suppress_presentation=voice_requested)

        if voice_requested:
            self.start_in_voice = False
            self.start_in_mini = False
            self._queue_voice_mode()
        elif getattr(self, "start_in_mini", False) or self.settings.get_string("startup-mode") == "mini":
            self.settings.set_string("startup-mode", "normal")
            # --mini is per-invocation: a later plain `newelle` must present the main window
            self.start_in_mini = False
            if getattr(self.win, "ui_built", False):
                self.show_mini_window()
                self.win.hide()
            else:
                self.win.connect("ui-built", self.show_mini_window)
        else:
            if getattr(self, "voice_win", None) is not None:
                self.voice_win.cancel()
            self._present_main_window()

    def _queue_voice_mode(self):
        """Toggle Voice Mode now, or once the hidden main controller is ready."""
        if getattr(self.win, "ui_built", False):
            self.show_voice_mode()
            return
        if getattr(self, "_voice_start_pending", False):
            self._voice_start_pending = False
            return
        self._voice_start_pending = True
        self.win.connect("ui-built", self._show_queued_voice_mode)

    def _show_queued_voice_mode(self, *_args):
        if not getattr(self, "_voice_start_pending", False):
            return
        self._voice_start_pending = False
        self.show_voice_mode()

    def show_voice_mode(self, *_args):
        """Open or cancel the one-shot desktop Voice Mode surface."""
        existing = getattr(self, "voice_win", None)
        if existing is not None:
            if existing.is_closing() or existing.get_visible():
                existing.cancel()
                return
        self.voice_win = VoiceModeWindow(
            application=self,
            main_window=self.win,
            on_closed=self._voice_mode_closed,
        )
        self.voice_win.present()
        GLib.idle_add(self.voice_win.start)

    def _voice_mode_closed(self, window):
        if getattr(self, "voice_win", None) is window:
            self.voice_win = None

    def toggle_voice_mode(self, *_args):
        if self.win is None:
            self.start_in_voice = True
            self.activate()
            return
        self._queue_voice_mode()

    def show_mini_window(self, *args):
        """Open the mini window hosting the chat panel of the main window"""
        if getattr(self, "mini_win", None) is not None and self.mini_win.get_visible():
            self.mini_win.close()
        self.mini_win = MiniWindow(application=self, main_window=self.win)
        self.mini_win.present()
        GLib.idle_add(activate_macos_application)

    def toggle_mini_window(self, *a):
        """Switch between the mini window and the full window"""
        if getattr(self, "mini_win", None) is not None and self.mini_win.is_active():
            # From the mini window: give the panel back and show the full window
            self.mini_win.close()
            self.win.present()
        else:
            # From the full window: host the chat panel in the mini window instead
            self.show_mini_window()
            self.win.hide()

    def focus_message(self, *a):
        self._present_main_window()
        self.win.focus_input()

    def reload_chat(self,*a):
        self._present_main_window()
        self.win.show_chat()
        self.win.notification_block.add_toast(
                Adw.Toast(title=_('Chat is rebooted')))

    def reload_folder(self,*a):
        self._present_main_window()
        self.win.update_folder()
        self.win.notification_block.add_toast(
                Adw.Toast(title=_('Folder is rebooted')))

    def new_chat(self,*a):
        self._present_main_window()
        self.win.new_chat(None)
        self.win.notification_block.add_toast(
                Adw.Toast(title=_('Chat is created')))

    def new_chat_tab(self, *a):
        self._present_main_window()
        self.win._on_create_chat_tab(None)

    def new_explorer_tab(self, *a):
        self._present_main_window()
        self.win.add_explorer_tab()

    def new_terminal_tab(self, *a):
        self._present_main_window()
        self.win.add_terminal_tab()

    def new_browser_tab(self, *a):
        self._present_main_window()
        self.win.add_browser_tab()

    def open_mini_window(self, *a):
        self._ensure_main_window()
        self.show_mini_window()

    def start_recording(self,*a):
        tab = self.win.get_active_chat_tab()
        if tab is None:
            return
        if not self.win.recording:
            self.win.start_recording(tab.recording_button)
        else:
            self.win.stop_recording(tab.recording_button)

    def stop_tts(self,*a):
        self.win.mute_tts(self.win.mute_tts_button)

    def stop_chat(self, *a):
        if self.win is not None and not self.win.status:
            self.win.stop_chat()

    def close_active_window(self, *a):
        window = self.props.active_window or getattr(self, "win", None)
        if window is None:
            return
        if window is self.win:
            window.close_active_chat_tab_or_window()
            return
        window.close()

    def quit_application(self, *a):
        for window in list(self.main_windows):
            window.close()
        if not self.main_windows:
            self.quit()
    
    def do_shutdown(self):
        from .utility.command_runner import shutdown_command_executions
        from .utility.command_sessions import shutdown_command_sessions

        shutdown_command_executions()
        shutdown_command_sessions()
        ready_windows = [window for window in self.main_windows if getattr(window, "ui_built", False)]
        if not ready_windows:
            Gtk.Application.do_shutdown(self)
            return
        active = self.win if self.win in ready_windows else ready_windows[-1]
        active.save_chat()
        settings = Gio.Settings.new('io.github.qwersyk.Newelle')
        settings.set_int("chat", active.chat_id)
        for window in ready_windows:
            window.save_workspace_tabs()
            window.stream_number_variable += 1
            window.controller.close_application()
        Gtk.Application.do_shutdown(self)

    def zoom(self, *a):
        zoom = min(250, self.win.settings.get_int("zoom") + 10)
        self.win.set_zoom(zoom)
        self.win.settings.set_int("zoom", zoom)

    def zoom_out(self, *a):
        zoom = max(100, self.win.settings.get_int("zoom") - 10)
        self.win.set_zoom(zoom)
        self.win.settings.set_int("zoom", zoom)
    
    def save(self, *a):
        self.win.save()
    def pretty_print_chat(self, *a):
        for msg in self.win.chat:
            print(msg["User"], msg["Message"])
    def debug(self, *a):
        self.pretty_print_chat()
        print(convert_history_openai(self.win.chat, [], True))

def run_headless(interface_key, version):
    """Start an interface without the GUI."""
    from .controller import NewelleController
    from .constants import AVAILABLE_INTERFACES

    if interface_key not in AVAILABLE_INTERFACES:
        available = ", ".join(AVAILABLE_INTERFACES.keys())
        print(f"Unknown interface '{interface_key}'. Available: {available}", file=sys.stderr)
        return 1

    info = AVAILABLE_INTERFACES[interface_key]
    print(f"Starting {info['title']} (headless)...")

    controller = NewelleController(sys.path)
    controller.ui_init()
    controller.handlers.load_handlers()
    controller.handlers.select_handlers(controller.newelle_settings, skip_auto_start_interfaces=True)
    ui_controller = HeadlessController(controller)
    controller.set_ui_controller(ui_controller)

    from .utility.replacehelper import ReplaceHelper
    ReplaceHelper.set_controller(controller)

    iface = controller.handlers.get_object(AVAILABLE_INTERFACES, interface_key, False)
    if iface is None:
        print(f"Failed to initialize interface '{interface_key}'", file=sys.stderr)
        return 1

    iface.start()
    if not iface.is_running():
        print(f"Interface '{interface_key}' failed to start", file=sys.stderr)
        return 1

    print(f"{info['title']} is running. Press Ctrl+C to stop.")

    # Run a GLib_MainLoop so GLib.idle_add (used by tool execution, etc.) works
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nStopping interface...")
        iface.stop()
    return 0


def create_application(version):
    app = MyApp(application_id="io.github.qwersyk.Newelle.macos", version = version)
    app.create_action('reload_chat', app.reload_chat, [primary_accel("r")])
    app.create_action('reload_folder', app.reload_folder, [primary_accel("e")])
    app.create_action('new_chat', app.new_chat, [primary_accel("n")])
    app.create_action('new_chat_tab', app.new_chat_tab, [primary_accel("t")])
    app.create_action('new_explorer_tab', app.new_explorer_tab)
    app.create_action('new_terminal_tab', app.new_terminal_tab)
    app.create_action('new_browser_tab', app.new_browser_tab)
    app.create_action('open_mini_window', app.open_mini_window, [primary_accel("<Shift>m")])
    app.create_action('close_active_window', app.close_active_window, [primary_accel("w")])
    app.create_action('quit', app.quit_application, [primary_accel("q")])
    app.create_action('focus_message', app.focus_message, [primary_accel("l")])
    app.create_action('start_recording', app.start_recording, [primary_accel("<Shift>r")])
    app.create_action('stop_chat', app.stop_chat, [primary_accel("period"), "Escape"])
    app.create_action('stop_tts', app.stop_tts, [primary_accel("k")])
    app.create_action('save', app.save, [primary_accel("s")])
    app.create_action('zoom', app.zoom, [primary_accel("plus"), primary_accel("equal")])
    app.create_action('zoom_out', app.zoom_out, [primary_accel("minus")])
    app.create_action('debug', app.debug, [primary_accel("b")])
    app.create_action('toggle_mini_window', app.toggle_mini_window, [primary_accel("d")])
    app.create_action("voice_mode", app.toggle_voice_mode, [primary_accel("i")])
    app.set_action_shortcuts("preferences", [primary_accel("comma")])
    app.set_action_shortcuts("shortcuts", ["<Shift>" + primary_accel("slash")])
    return app


def main(version):
    return create_application(version).run(sys.argv)
