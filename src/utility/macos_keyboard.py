"""Translate Command shortcuts using macOS's active keyboard layout."""

import ctypes
import ctypes.util
from functools import lru_cache
import sys


@lru_cache(maxsize=1)
def _keyboard_api():
    carbon = ctypes.CDLL(ctypes.util.find_library("Carbon"))
    core = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
    pointer = ctypes.c_void_p
    uint32_pointer = ctypes.POINTER(ctypes.c_uint32)
    ulong_pointer = ctypes.POINTER(ctypes.c_ulong)
    signatures = (
        (carbon, "TISCopyCurrentKeyboardLayoutInputSource", pointer, []),
        (carbon, "TISCopyCurrentASCIICapableKeyboardLayoutInputSource", pointer, []),
        (carbon, "TISGetInputSourceProperty", pointer, [pointer, pointer]),
        (carbon, "LMGetKbdType", ctypes.c_uint8, []),
        (carbon, "UCKeyTranslate", ctypes.c_int32,
         [pointer, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint32,
          ctypes.c_uint32, ctypes.c_uint32, uint32_pointer, ctypes.c_ulong,
          ulong_pointer, ctypes.POINTER(ctypes.c_uint16)]),
        (core, "CFDataGetBytePtr", pointer, [pointer]),
        (core, "CFRelease", None, [pointer]),
    )
    for library, name, result, arguments in signatures:
        function = getattr(library, name)
        function.restype = result
        function.argtypes = arguments
    layout_property = pointer.in_dll(carbon, "kTISPropertyUnicodeKeyLayoutData")
    return carbon, core, layout_property


def command_key_character(keycode):
    """Return the letter macOS assigns to Command plus this hardware key.

    GTK's macOS keymap only translates Shift and Option, omitting the Command
    table. That table maps Russian and other non-Latin layouts to shortcuts,
    and also preserves layouts such as AZERTY and Dvorak-QWERTY Command.
    Fetch the input source on every shortcut so layout changes apply at once.
    """
    if sys.platform != "darwin" or keycode is None or not 0 <= keycode < 128:
        return None
    try:
        carbon, core, layout_property = _keyboard_api()
    except (OSError, AttributeError, ValueError):
        return None

    for copy_source in (carbon.TISCopyCurrentKeyboardLayoutInputSource,
                        carbon.TISCopyCurrentASCIICapableKeyboardLayoutInputSource):
        source = copy_source()
        if not source:
            continue
        try:
            data = carbon.TISGetInputSourceProperty(source, layout_property)
            if not data:
                continue
            dead_key = ctypes.c_uint32()
            length = ctypes.c_ulong()
            output = (ctypes.c_uint16 * 4)()
            # kUCKeyActionDown = 0; cmdKey >> 8 = 1;
            # kUCKeyTranslateNoDeadKeysMask = 1. Do not alter text input state.
            status = carbon.UCKeyTranslate(
                core.CFDataGetBytePtr(data), keycode, 0, 1, carbon.LMGetKbdType(),
                1, ctypes.byref(dead_key), len(output), ctypes.byref(length), output,
            )
            if status == 0 and length.value == 1:
                character = chr(output[0]).lower()
                if "a" <= character <= "z":
                    return character
        finally:
            core.CFRelease(source)
    return None
