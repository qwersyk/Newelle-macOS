"""Shared Newelle artwork for application windows and empty states."""

from gi.repository import Adw, Gtk

_ICON_NAME = "io.github.qwersyk.Newelle"


def app_icon_name():
    return _ICON_NAME + ("-dark" if Adw.StyleManager.get_default().get_dark() else "")


def bind_app_icon(widget, property_name="icon-name"):
    def update(target, *_args):
        target.set_property(property_name, app_icon_name())

    update(widget)
    Adw.StyleManager.get_default().connect_object("notify::dark", update, widget)


def app_logo(pixel_size=128, **kwargs):
    image = Gtk.Image(pixel_size=pixel_size, **kwargs)
    bind_app_icon(image)
    return image
