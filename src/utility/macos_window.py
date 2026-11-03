"""Small AppKit operations on an explicitly selected GTK window."""

import sys


def native_window(window):
    if sys.platform != "darwin" or window.get_surface() is None:
        return None
    import ctypes
    import ctypes.util
    import objc

    capsule_pointer = ctypes.pythonapi.PyCapsule_GetPointer
    capsule_pointer.restype = ctypes.c_void_p
    capsule_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    library = ctypes.CDLL(ctypes.util.find_library("gtk-4.1") or "libgtk-4.1.dylib")
    get_window = library.gdk_macos_surface_get_native_window
    get_window.restype = ctypes.c_void_p
    get_window.argtypes = [ctypes.c_void_p]
    pointer = get_window(capsule_pointer(window.get_surface().__gpointer__, None))
    return objc.objc_object(c_void_p=pointer) if pointer else None


def float_mini_window(window):
    native = native_window(window)
    if native is None:
        return
    from AppKit import NSFloatingWindowLevel, NSWindowCollectionBehaviorMoveToActiveSpace

    native.setLevel_(NSFloatingWindowLevel)
    native.setCollectionBehavior_(
        native.collectionBehavior() | NSWindowCollectionBehaviorMoveToActiveSpace
    )


def configure_native_window(window, *_args):
    """Keep normal windows filled while AppKit animates their frame."""
    if not window.get_decorated():
        return
    native = native_window(window)
    if native is None:
        return
    from AppKit import NSColor

    found, color = window.get_style_context().lookup_color("window_bg_color")
    background = (NSColor.colorWithRed_green_blue_alpha_(color.red, color.green, color.blue, 1.0)
                  if found else NSColor.windowBackgroundColor())
    native.setBackgroundColor_(background)
    native.setOpaque_(True)
    native.setPreservesContentDuringLiveResize_(True)


def install_native_window_behavior(_application, window):
    if sys.platform != "darwin":
        return
    window.connect("map", configure_native_window)
