"""Oma File Explorer: reload our stylesheet inside Nautilus only."""
import os
from pathlib import Path

import gi
gi.require_version("Nautilus", "4.1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, GObject, Gtk, Nautilus


class OmaFileExplorerStyle(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        super().__init__()
        config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.path = config / "oma-file-explorer" / "style.css"
        self.provider = Gtk.CssProvider()
        self.display = Gdk.Display.get_default()
        self.settings = Gtk.Settings.get_default()
        self.stamp = None
        if self.display:
            # Below user CSS, above application styles. Existing user CSS wins.
            Gtk.StyleContext.add_provider_for_display(self.display, self.provider, 700)
            self.reload()
            self.timer = GLib.timeout_add_seconds(2, self.reload)

    def reload(self):
        try:
            stat = self.path.stat()
            stamp = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
            if stamp != self.stamp:
                stylesheet = self.path.read_text()
                self.provider.load_from_data(stylesheet.encode())
                if "/* oma-file-explorer: active */" in stylesheet:
                    # Portals can lag behind the icon setting. Also invalidate
                    # cached SVGs when the generated palette changes.
                    self.settings.set_property("gtk-icon-theme-name", "Adwaita")
                    self.settings.set_property("gtk-icon-theme-name", "OmaFileExplorer")
                else:
                    self.settings.reset_property("gtk-icon-theme-name")
                self.stamp = stamp
        except FileNotFoundError:
            if self.stamp is not None:
                self.provider.load_from_data(b"")
                self.settings.reset_property("gtk-icon-theme-name")
                self.stamp = None
        except (OSError, GLib.Error) as error:
            print(f"Oma File Explorer: {error}")
        return GLib.SOURCE_CONTINUE

    def get_file_items(self, files):
        return []

    def get_background_items(self, current_folder):
        return []
