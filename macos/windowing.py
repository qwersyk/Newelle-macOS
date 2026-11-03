"""App-local workarounds for macOS windowing regressions."""
from __future__ import annotations

import os
import platform
import time

_installed = False
_monitor = None
_drag = None
_mouse_down = None


def needs_manual_window_drag(version=None):
    override = os.getenv("NEWELLE_MANUAL_WINDOW_DRAG")
    if override is not None:
        return override == "1"
    version = platform.mac_ver()[0] if version is None else version
    return version.split(".")[:2] == ["27", "2"]


def drag_origin(start_origin, start_mouse, mouse):
    return (start_origin[0] + mouse[0] - start_mouse[0],
            start_origin[1] + mouse[1] - start_mouse[1])


def fallback_snap_frame(visible, screen, mouse, minimum, margin=10):
    """Geometry for a failed native drag; never tile below the window minimum."""
    x, y, width, height = visible
    sx, sy, sw, sh = screen
    mx, my = mouse
    if not (sx <= mx <= sx + sw and sy <= my <= sy + sh):
        return None
    if my >= sy + sh - margin:
        target = (x, y, width, height)
    elif mx <= sx + margin:
        target = (x, y, width / 2, height)
    elif mx >= sx + sw - margin:
        target = (x + width / 2, y, width / 2, height)
    else:
        return None
    if target[2] < minimum[0] or target[3] < minimum[1]:
        return None
    return target


def install_window_drag_workaround():
    """Give AppKit the original press so native tiling and Spaces remain active.

    GTK starts the drag after the pointer moves, passing a motion event.
    AppKit documents that this handoff needs the original mouse-down event.
    Manual movement is only a fallback for the macOS 27.2 regression.
    """
    global _installed, _monitor
    if _installed:
        return True

    import objc
    from AppKit import (
        NSEvent, NSEventMaskLeftMouseDown, NSEventMaskLeftMouseDragged, NSEventMaskLeftMouseUp,
        NSEventTypeLeftMouseDown, NSEventTypeLeftMouseUp, NSMakePoint, NSMakeRect, NSScreen,
        NSWindowStyleMaskFullScreen,
    )

    native_class = objc.lookUpClass("GdkMacosWindow")
    allow_fallback = needs_manual_window_drag()

    def screen_at(mouse, window):
        for screen in NSScreen.screens():
            rect = screen.frame()
            if (rect.origin.x <= mouse.x < rect.origin.x + rect.size.width
                    and rect.origin.y <= mouse.y < rect.origin.y + rect.size.height):
                return screen
        return window.screen()

    def rect_tuple(rect):
        return (rect.origin.x, rect.origin.y, rect.size.width, rect.size.height)

    def begin_native_drag(window, event):
        global _drag
        if window.styleMask() & NSWindowStyleMaskFullScreen:
            return
        press = _mouse_down
        if press is None or press.windowNumber() != window.windowNumber():
            press = event
        mouse, origin = NSEvent.mouseLocation(), window.frame().origin
        _drag = {
            "window": window, "origin": (origin.x, origin.y),
            "mouse": (mouse.x, mouse.y), "started": time.monotonic(),
            "fallback": False, "native_moved": False,
        }
        # Keep GDK's own beginManualMove bookkeeping and only replace the
        # event passed to NSWindow, rather than overriding GTK's move method.
        objc.super(native_class, window).performWindowDragWithEvent_(press)

    def track(event):
        global _drag, _mouse_down
        if event.type() == NSEventTypeLeftMouseDown:
            _mouse_down, _drag = event, None
            return event
        if _drag is None:
            return event
        state = _drag
        window = state["window"]
        mouse = NSEvent.mouseLocation()
        if event.type() == NSEventTypeLeftMouseUp:
            _drag = _mouse_down = None
            if state["fallback"] and window.isVisible() and window.isResizable():
                screen = screen_at(mouse, window)
                if screen is not None:
                    size = window.minSize()
                    target = fallback_snap_frame(
                        rect_tuple(screen.visibleFrame()), rect_tuple(screen.frame()),
                        (mouse.x, mouse.y), (size.width, size.height),
                    )
                    if target is not None:
                        window.setFrame_display_animate_(NSMakeRect(*target), True, True)
            return event
        if not window.isVisible() or not (NSEvent.pressedMouseButtons() & 1):
            _drag = None
            return event
        current = window.frame().origin
        origin = state["origin"]
        if not state["fallback"]:
            if abs(current.x - origin[0]) > 1 or abs(current.y - origin[1]) > 1:
                state["native_moved"] = True
            if state["native_moved"] or not allow_fallback or time.monotonic() - state["started"] < 0.15:
                return event
            state["fallback"] = True
        x, y = drag_origin(origin, state["mouse"], (mouse.x, mouse.y))
        screen = screen_at(mouse, window)
        if screen is not None:
            visible = screen.visibleFrame()
            highest = max(origin[1], visible.origin.y + visible.size.height - window.frame().size.height)
            y = min(y, highest)
        if abs(current.x - x) >= 0.01 or abs(current.y - y) >= 0.01:
            window.setFrameOrigin_(NSMakePoint(x, y))
        return event

    _monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        NSEventMaskLeftMouseDown | NSEventMaskLeftMouseDragged | NSEventMaskLeftMouseUp, track,
    )
    if _monitor is None:
        return False
    objc.classAddMethods(native_class, [
        objc.selector(begin_native_drag, selector=b"performWindowDragWithEvent:", signature=b"v@:@"),
    ])
    _installed = True
    return True
