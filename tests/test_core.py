import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("oma", ROOT / "oma_file_explorer.py")
oma = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oma)


class StylingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_STATE_HOME": str(self.root / "state"),
        })
        env.start()
        self.addCleanup(env.stop)
        self.paths = oma.Paths()
        self.theme = self.root / "state/omarchy/current/theme"
        self.theme.mkdir(parents=True)
        self.set_palette()
        (self.theme / "icons.theme").write_text("Yaru-blue\n")
        self.icon_setting = "Yaru-blue"
        getter = patch.object(oma, "settings_get", side_effect=lambda: self.icon_setting)
        setter = patch.object(oma, "settings_set", side_effect=self.set_icons)
        # Cache generation is exercised separately against actual GTK tooling.
        which = patch.object(oma.shutil, "which", return_value=None)
        for mock in (getter, setter, which):
            mock.start()
            self.addCleanup(mock.stop)

    def set_icons(self, value):
        self.icon_setting = value

    def set_palette(self, background="#111c18", foreground="#c1c497", accent="#509475"):
        (self.theme / "colors.toml").write_text(
            f'background = "{background}"\nforeground = "{foreground}"\naccent = "{accent}"\n')

    def test_apply_preserves_user_css_and_repeated_apply_does_not_rewrite(self):
        existing = self.paths.config / "gtk-4.0/gtk.css"
        existing.parent.mkdir(parents=True)
        existing.write_text("/* my existing theme */\n")
        self.assertTrue(oma.apply(self.paths))
        stamp = self.paths.css.stat().st_mtime_ns
        self.assertFalse(oma.apply(self.paths))
        self.assertEqual(stamp, self.paths.css.stat().st_mtime_ns)
        self.assertEqual(existing.read_text(), "/* my existing theme */\n")
        self.assertEqual(self.icon_setting, oma.ICON_THEME)

    def test_theme_changes_recolor_folders_and_restore_current_theme(self):
        oma.apply(self.paths)
        icon = self.paths.icons / "scalable/places/folder.svg"
        before = icon.read_text()
        self.set_palette("#eeeeee", "#222222", "#cc2255")
        (self.theme / "icons.theme").write_text("Yaru-red")
        self.icon_setting = "Yaru-red"  # Omarchy resets this during theme-set.
        oma.apply(self.paths, resume=False)
        self.assertNotEqual(before, icon.read_text())
        self.assertIn(oma.mix("#eeeeee", "#cc2255", .12), icon.read_text())
        oma.restore(self.paths)
        self.assertEqual(self.icon_setting, "Yaru-red")
        self.assertNotIn("--window-bg-color", self.paths.css.read_text())
        self.assertFalse(oma.apply(self.paths, resume=False))
        oma.apply(self.paths)
        self.assertEqual(self.icon_setting, oma.ICON_THEME)

    def test_restore_does_not_overwrite_a_later_icon_choice(self):
        oma.apply(self.paths)
        self.icon_setting = "My-own-icons"
        oma.restore(self.paths)
        self.assertEqual(self.icon_setting, "My-own-icons")

    def test_restore_without_active_theme_uses_original_icons(self):
        oma.apply(self.paths)
        (self.theme / "colors.toml").unlink()
        oma.restore(self.paths)
        self.assertEqual(self.icon_setting, "Yaru-blue")

    def test_rejects_invalid_palette_before_installation(self):
        self.set_palette(accent="red; background: white")
        with self.assertRaises(ValueError):
            oma.apply(self.paths)
        self.assertFalse(self.paths.record.exists())
        self.assertFalse(self.paths.extension.exists())

    def test_refuses_unknown_files_and_symlinks(self):
        self.paths.css.parent.mkdir(parents=True)
        unrelated = self.root / "unrelated"
        unrelated.write_text("keep me")
        self.paths.css.symlink_to(unrelated)
        with self.assertRaises(ValueError):
            oma.apply(self.paths)
        self.assertEqual(unrelated.read_text(), "keep me")
        self.assertFalse(self.paths.extension.exists())

    def test_palette_contrast_on_light_and_dark_themes(self):
        for bg, fg, accent in (("#fafafa", "#dddddd", "#eeeeee"), ("#101010", "#333333", "#222222")):
            self.set_palette(bg, fg, accent)
            colors = oma.palette(self.theme)
            self.assertGreaterEqual(oma.contrast(accent, colors["on_accent"]), 4.5)
            self.assertGreaterEqual(oma.contrast(colors["selection"], colors["on_selection"]), 4.5)

    def test_generated_icons_are_valid_and_keep_inherited_file_icons(self):
        _, icons = oma.render(self.theme, "Yaru-blue")
        self.assertIn("Inherits=Yaru-blue,Adwaita,hicolor", icons["index.theme"])
        self.assertIn("scalable/mimetypes/inode-directory.svg", icons)
        for path, svg in icons.items():
            if path.endswith(".svg"):
                root = ET.fromstring(svg)
                self.assertEqual(root.attrib["viewBox"], "0 0 16 16" if "-symbolic" in path else "0 0 64 64")
        self.assertEqual(len([p for p in icons if p.endswith(".svg")]), 34)

    def test_preview_has_no_desktop_side_effects_and_refuses_overwrite(self):
        output = self.root / "preview"
        oma.preview(self.theme, output)
        ET.parse(output / "folders.svg")
        self.assertFalse(self.paths.record.exists())
        self.assertEqual(self.icon_setting, "Yaru-blue")
        with self.assertRaises(FileExistsError):
            oma.preview(self.theme, output)

    def test_legacy_theme_location(self):
        legacy = self.paths.config / "omarchy/current/theme"
        legacy.parent.mkdir(parents=True)
        self.theme.rename(legacy)
        self.assertEqual(self.paths.theme(), legacy)


if __name__ == "__main__":
    unittest.main()
