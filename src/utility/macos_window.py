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
