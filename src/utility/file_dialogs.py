"""Keep asynchronous native file panels tied to their visible GTK owner."""

from gi.repository import Gio, Gtk


def show_file_dialog(dialog, operation, parent, callback, *user_data):
    if parent is not None and not isinstance(parent, Gtk.Window):
        parent = parent.get_root()
    if parent is not None:
        # A mini window hosts the chat, but its controller belongs to the main window.
        mini = getattr(parent.get_application(), "mini_win", None)
        if mini is not None and mini.main_window is parent and mini.get_mapped():
            parent = mini
    pending = getattr(parent, "_newelle_file_dialog", None)
    if pending is not None:
        return pending

    cancellable = Gio.Cancellable()
    handlers = []
    if parent is not None:
        parent._newelle_file_dialog = cancellable
        if hasattr(parent, "close_transient_ui"):
            parent.close_transient_ui()
        for signal in ("unmap", "destroy"):
            handlers.append(parent.connect(signal, lambda *_: cancellable.cancel()))

    def release():
        if parent is not None:
            if getattr(parent, "_newelle_file_dialog", None) is cancellable:
                parent._newelle_file_dialog = None
            for handler in handlers:
                if parent.handler_is_connected(handler):
                    parent.disconnect(handler)
            handlers.clear()

    def finished(source, result):
        release()
        callback(source, result, *user_data)

    try:
        getattr(dialog, operation)(parent, cancellable, finished)
    except Exception:
        release()
        raise
    return cancellable


def cancel_file_dialog(window):
    cancellable = getattr(window, "_newelle_file_dialog", None)
    if cancellable is not None:
        cancellable.cancel()
