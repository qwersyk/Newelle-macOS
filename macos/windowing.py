"""App-local workarounds for macOS windowing regressions."""
from __future__ import annotations

import os
import platform

_installed = False
_monitor = None
_drag = None


def needs_manual_window_drag(version=None):
    override = os.getenv("NEWELLE_MANUAL_WINDOW_DRAG")
    if override is not None:
        return override == "1"
    # macOS 27.2 can drop AppKit's performWindowDragWithEvent handoff.
    # Keep this scoped so other OS versions retain native snapping/Spaces.
    version = platform.mac_ver()[0] if version is None else version
    return version.split(".")[:2] == ["27", "2"]


def drag_origin(start_origin, start_mouse, mouse):
    return (start_origin[0] + mouse[0] - start_mouse[0],
            start_origin[1] + mouse[1] - start_mouse[1])


def install_window_drag_workaround():
    """Let GTK identify draggable regions, then track the drag in AppKit.

    This covers all GTK windows, including preferences. It replaces only
    GDK's native drag handoff, leaving buttons, hit testing and resize intact.
    See https://github.com/warpdotdev/warp/issues/16508 for the OS regression.
    """
    global _installed, _monitor
    if _installed or not needs_manual_window_drag():
        return _installed

    import objc
    from AppKit import (
        NSEvent, NSEventMaskLeftMouseDown, NSEventMaskLeftMouseDragged, NSEventMaskLeftMouseUp,
        NSEventTypeLeftMouseDown, NSEventTypeLeftMouseUp, NSMakePoint, NSScreen,
        NSWindowStyleMaskFullScreen,
    )

    native_window_class = objc.lookUpClass("GdkMacosWindow")

    def begin_manual_move(window):
        global _drag
        if window.styleMask() & NSWindowStyleMaskFullScreen:
            return
        mouse = NSEvent.mouseLocation()
        origin = window.frame().origin
        _drag = (window, (origin.x, origin.y), (mouse.x, mouse.y))
        if os.getenv("NEWELLE_DEBUG_WINDOWING") == "1":
            print("Manual native window drag started", flush=True)

    def track(event):
        global _drag
        if event.type() == NSEventTypeLeftMouseDown:
            _drag = None
            return event
        if _drag is None:
            return event
        if event.type() == NSEventTypeLeftMouseUp:
            _drag = None
            return event
        window, origin, start_mouse = _drag
        if not window.isVisible() or not (NSEvent.pressedMouseButtons() & 1):
            _drag = None
            return event
        mouse = NSEvent.mouseLocation()
        x, y = drag_origin(origin, start_mouse, (mouse.x, mouse.y))
        size = window.frame().size
        screen = window.screen()
        for candidate in NSScreen.screens():
            frame = candidate.frame()
            if (frame.origin.x <= mouse.x < frame.origin.x + frame.size.width
                    and frame.origin.y <= mouse.y < frame.origin.y + frame.size.height):
                screen = candidate
                break
        if screen is not None:
            # Keep the top of the window reachable below the menu bar.
            visible = screen.visibleFrame()
            # Preserve any existing title-bar overhang when the grab starts;
            # clamping an already positioned window causes a small first-frame jump.
            highest_origin = max(origin[1], visible.origin.y + visible.size.height - size.height)
            y = min(y, highest_origin)
        current = window.frame().origin
        if abs(current.x - x) < 0.01 and abs(current.y - y) < 0.01:
            return event
        window.setFrameOrigin_(NSMakePoint(x, y))
        if os.getenv("NEWELLE_DEBUG_WINDOWING") == "1":
            print("Manual native window drag moved", flush=True)
        return event

    _monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        NSEventMaskLeftMouseDown | NSEventMaskLeftMouseDragged | NSEventMaskLeftMouseUp, track,
    )
    if _monitor is None:
        return False
    objc.classAddMethods(native_window_class, [
        objc.selector(begin_manual_move, selector=b"beginManualMove", signature=b"v@:"),
    ])
    _installed = True
    return True
