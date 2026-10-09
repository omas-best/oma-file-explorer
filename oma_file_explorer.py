#!/usr/bin/env python3
"""Omarchy colors and original SVG folders for the existing Files application."""
import argparse
import ast
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from string import Template
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parent
PLUGIN_ID = "community.oma-file-explorer"
ICON_THEME = "OmaFileExplorer"
EXTENSION = "oma_file_explorer_style.py"
SCHEMA = "org.gnome.desktop.interface"


def xdg(name, default):
    return Path(os.environ.get(name, Path.home() / default)).expanduser()


class Paths:
    def __init__(self):
        self.config = xdg("XDG_CONFIG_HOME", ".config")
        self.data = xdg("XDG_DATA_HOME", ".local/share")
        self.state = xdg("XDG_STATE_HOME", ".local/state") / "oma-file-explorer"
        self.css = self.config / "oma-file-explorer/style.css"
        self.icons = self.data / "icons" / ICON_THEME
        self.extension = self.data / "nautilus-python/extensions" / EXTENSION
        self.plugin = self.config / "omarchy/plugins" / PLUGIN_ID
        self.record = self.state / "state.json"

    def theme(self):
        candidates = [
            xdg("XDG_STATE_HOME", ".local/state") / "omarchy/current/theme",
            self.config / "omarchy/current/theme",
        ]
        for directory in candidates:
            if (directory / "colors.toml").is_file():
                return directory
        raise ValueError("No active Omarchy colors.toml found. Select an Omarchy theme first.")


def read(path, default=""):
    return path.read_text() if path.exists() else default


def atomic_write(path, content, mode=0o644):
    """Replace a managed file, without rewriting unchanged output."""
    if path.is_symlink():
        raise ValueError(f"Refusing to replace a symbolic link: {path}")
    if path.exists() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".oma-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


@contextmanager
def locked(paths):
    paths.state.mkdir(parents=True, exist_ok=True)
    with (paths.state / "lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def settings_get():
    result = subprocess.run(["gsettings", "get", SCHEMA, "icon-theme"],
                            capture_output=True, text=True, check=True)
    return ast.literal_eval(result.stdout.strip())


def settings_set(value):
    subprocess.run(["gsettings", "set", SCHEMA, "icon-theme", value], check=True,
                   capture_output=True, text=True)
    if settings_get() != value:
        raise ValueError("The desktop did not save the icon theme. Run this inside your desktop session.")


def rgb(color):
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))


def luminance(color):
    channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb(color)]
    return sum(v * w for v, w in zip(channels, (.2126, .7152, .0722)))


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + .05) / (low + .05)


def mix(a, b, weight):
    return "#" + "".join(f"{round((x * (1 - weight) + y * weight) * 255):02x}"
                         for x, y in zip(rgb(a), rgb(b)))


def readable(background, preferred):
    if contrast(background, preferred) >= 4.5:
        return preferred
    return max(("#ffffff", "#111111"), key=lambda color: contrast(background, color))


def palette(theme):
    with (theme / "colors.toml").open("rb") as stream:
        raw = tomllib.load(stream)
    colors = {}
    for key in ("background", "foreground", "accent"):
        value = raw.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError(f"colors.toml needs a six-digit hex {key} color")
        colors[key] = value.lower()
    for key in ("selection", "dark_background", "lighter_background"):
        value = raw.get(key)
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value)):
            raise ValueError(f"Invalid {key} color")
    bg, fg, accent = (colors[key] for key in ("background", "foreground", "accent"))
    colors.update(
        surface=raw.get("dark_background", mix(bg, fg, .035)),
        raised=raw.get("lighter_background", mix(bg, fg, .08)),
        selection=raw.get("selection", mix(bg, accent, .28)),
        border=mix(bg, fg, .22),
        on_accent=readable(accent, fg),
        link=accent if contrast(bg, accent) >= 4.5 else readable(bg, fg),
    )
    colors["on_selection"] = readable(colors["selection"], fg)
    return colors


# These small geometric badges and folder silhouettes are original artwork.
BADGES = {
    "folder": "",
    "folder-open": "",
    "folder-documents": '<path d="M27 28h8l5 5v14H27z M35 28v6h5 M30 38h7 M30 42h7"/>',
    "folder-download": '<path d="M32 28v15m-6-6 6 6 6-6M24 47h16"/>',
    "folder-pictures": '<rect x="23" y="29" width="20" height="17" rx="2"/><path d="m24 43 6-6 5 4 4-3 4 5"/><circle cx="37" cy="34" r="1"/>',
    "folder-music": '<path d="M29 43V30l12-3v13 M29 34l12-3"/><ellipse cx="26" cy="44" rx="3" ry="2"/><ellipse cx="38" cy="41" rx="3" ry="2"/>',
    "folder-videos": '<rect x="23" y="29" width="20" height="17" rx="2"/><path d="m30 33 7 5-7 4z"/>',
    "folder-publicshare": '<circle cx="26" cy="34" r="3"/><circle cx="38" cy="34" r="3"/><path d="M20 46v-3a6 6 0 0 1 12 0v3M32 43a6 6 0 0 1 12 0v3"/>',
    "folder-templates": '<path stroke-dasharray="3 3" d="M24 29h18v18H24z"/>',
    "folder-remote": '<path d="M32 28v9M23 46v-9h18v9M32 37v9"/><path d="M28 28h8M19 46h8M28 46h8M37 46h8"/>',
    "folder-saved-search": '<circle cx="30" cy="35" r="6"/><path d="m35 40 6 6"/>',
    "user-home": '<path d="m22 37 11-9 11 9M26 35v12h14V35M31 47v-8h5v8"/>',
    "user-desktop": '<rect x="22" y="28" width="22" height="15" rx="1"/><path d="M33 43v5M27 48h12"/>',
}
ALIASES = {"inode-directory": "folder", "folder-downloads": "folder-download",
           "folder-visiting": "folder-open", "folder-drag-accept": "folder-open"}

# Sidebar glyphs are designed on a 16 px grid, rather than shrinking badges.
SYMBOLS = {
    "folder": '<path d="M2 5V3.5h4l2 2h6v7H2z"/>',
    "folder-open": '<path d="M2 7V3.5h4l2 2h5v2M2 7.5h12l-2 5H2z"/>',
    "folder-documents": '<path d="M4 2h5l3 3v9H4zM9 2v4h3M6 9h4M6 11.5h4"/>',
    "folder-download": '<path d="M8 2v8M4.5 7 8 10.5 11.5 7M3 11v3h10v-3"/>',
    "folder-pictures": '<rect x="2" y="3" width="12" height="10" rx="1"/><path d="m3 11 3.5-4 3 3 2-2 2.5 3"/>',
    "folder-music": '<path d="M6 11V3l7-1v8M6 6l7-1"/><ellipse cx="4" cy="12" rx="2" ry="1.5"/><ellipse cx="11" cy="11" rx="2" ry="1.5"/>',
    "folder-videos": '<rect x="2" y="3" width="12" height="10" rx="1"/><path d="m6 5.5 4 2.5-4 2.5z"/>',
    "folder-publicshare": '<circle cx="6" cy="5" r="2"/><path d="M2 13v-1a4 4 0 0 1 8 0v1M11 3a2 2 0 0 1 0 4M12 9a3 3 0 0 1 2 3v1"/>',
    "folder-templates": '<path stroke-dasharray="2 3" d="M3 2.5h10v11H3z"/>',
    "folder-remote": '<rect x="6" y="2" width="4" height="3" rx=".5"/><path d="M8 5v4M3 11V9h10v2"/><rect x="1" y="11" width="4" height="3" rx=".5"/><rect x="11" y="11" width="4" height="3" rx=".5"/>',
    "folder-saved-search": '<circle cx="7" cy="7" r="4"/><path d="m10 10 4 4"/>',
    "user-home": '<path d="m1.5 7 6.5-5.5L14.5 7M3.5 6v8H7v-4h2v4h3.5V6"/>',
    "user-desktop": '<rect x="1.5" y="2" width="13" height="9" rx="1"/><path d="M8 11v3M5 14h6"/>',
}


def icon_svg(colors, badge="", symbolic=False, name="folder"):
    name = ALIASES.get(name, name)
    if symbolic:
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
<g fill="none" stroke="#bebebe" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{SYMBOLS[name]}</g>
</svg>
'''
    fill = mix(colors["background"], colors["accent"], .12)
    tab = mix(colors["background"], colors["accent"], .26)
    ink = readable(fill, colors["foreground"])
    # A stepped tab behind a rounded front, all on a consistent optical grid.
    front = 'M7 26h50v23a4 4 0 0 1-4 4H11a4 4 0 0 1-4-4z'
    if name == "folder-open":
        front = 'M12 27h47l-6 23a4 4 0 0 1-4 3H9z'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
<g stroke="{ink}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
<path d="M7 27V17a3 3 0 0 1 3-3h14l7 7h23a3 3 0 0 1 3 3v25a4 4 0 0 1-4 4H11a4 4 0 0 1-4-4z" fill="{tab}"/>
<path d="{front}" fill="{fill}"/>
<g fill="none" transform="translate(0 2)">{badge}</g></g>
</svg>
'''


def icon_files(colors, inherited):
    if not re.fullmatch(r"[\w .-]+", inherited) or inherited == ICON_THEME:
        inherited = "Adwaita"
    files = {"index.theme": f"""[Icon Theme]
Name=Oma File Explorer
Comment=Folders that follow your Omarchy theme
Inherits={inherited},Adwaita,hicolor
Directories=scalable/places,scalable/mimetypes

[scalable/places]
Size=48
MinSize=16
MaxSize=512
Type=Scalable
Context=Places

[scalable/mimetypes]
Size=48
MinSize=16
MaxSize=512
Type=Scalable
Context=MimeTypes
"""}
    badges = dict(BADGES)
    badges.update({name: BADGES[target] for name, target in ALIASES.items()})
    for name, badge in badges.items():
        directory = "mimetypes" if name == "inode-directory" else "places"
        files[f"scalable/{directory}/{name}.svg"] = icon_svg(colors, badge, name=name)
        files[f"scalable/{directory}/{name}-symbolic.svg"] = icon_svg(colors, badge, symbolic=True, name=name)
    return files


def render(theme, inherited):
    colors = palette(theme)
    css = Template((ROOT / "templates/style.css").read_text()).substitute(colors)
    icons = icon_files(colors, inherited)
    revision = hashlib.sha256(json.dumps(icons, sort_keys=True).encode()).hexdigest()
    return f"/* Folder revision: {revision} */\n" + css, icons


def fallback_theme(theme, original):
    value = read(theme / "icons.theme").strip() or original or "Adwaita"
    return value if re.fullmatch(r"[\w .-]+", value) and value != ICON_THEME else "Adwaita"


def load_state(paths):
    return json.loads(read(paths.record, "{}"))


def save_state(paths, state):
    atomic_write(paths.record, json.dumps(state, indent=2) + "\n", 0o600)


def apply(paths, theme=None, resume=True):
    with locked(paths):
        state = load_state(paths)
        if state.get("paused") and not resume:
            return False
        theme = theme or paths.theme()
        current = settings_get()
        original = state.get("original_icons", current if current != ICON_THEME else "Adwaita")
        inherited = fallback_theme(theme, original)
        css, icons = render(theme, inherited)
        extension = (ROOT / "extension" / EXTENSION).read_text()
        # Refuse collisions before installing any content.
        if not state.get("owned"):
            for path in (paths.css, paths.icons, paths.extension):
                if path.exists() or path.is_symlink():
                    raise ValueError(f"Already exists and is not owned by Oma File Explorer: {path}")
            state.update(owned=True, original_icons=original, paused=False)
            save_state(paths, state)
        changed = atomic_write(paths.extension, extension)
        icon_changed = False
        for relative, content in icons.items():
            icon_changed = atomic_write(paths.icons / relative, content) or icon_changed
        if icon_changed:
            os.utime(paths.icons, None)
            if shutil.which("gtk-update-icon-cache"):
                subprocess.run(["gtk-update-icon-cache", "--force", "--ignore-theme-index", str(paths.icons)],
                               capture_output=True, text=True, check=True)
            # Invalidate already cached SVGs in running applications.
            if current == ICON_THEME:
                settings_set(inherited)
        if current != ICON_THEME or icon_changed:
            settings_set(ICON_THEME)
        # Publish the stylesheet only after every icon is ready for the loader.
        changed = atomic_write(paths.css, css) or changed
        state.update(paused=False, theme=str(theme), fallback_icons=inherited,
                     extension_hash=hashlib.sha256(extension.encode()).hexdigest())
        save_state(paths, state)
        return changed or icon_changed or current != ICON_THEME


def restore(paths):
    with locked(paths):
        state = load_state(paths)
        if not state.get("owned"):
            return
        # Pause first: the shell service must not reapply after an explicit restore.
        state["paused"] = True
        save_state(paths, state)
        atomic_write(paths.css, "/* Oma File Explorer is paused. */\n")
        if settings_get() == ICON_THEME:
            try:
                fallback = fallback_theme(paths.theme(), state["original_icons"])
            except ValueError:
                fallback = state["original_icons"]
            settings_set(fallback)


def watch(paths):
    last_error = None
    while True:
        try:
            apply(paths, resume=False)
            last_error = None
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            message = str(error)
            if message != last_error:
                print(message, file=sys.stderr, flush=True)
                last_error = message
        time.sleep(3)


def install(paths):
    if not shutil.which("omarchy") or not shutil.which("omarchy-shell"):
        raise ValueError("Install requires Omarchy with the Quickshell plugin system.")
    check = subprocess.run([sys.executable, "-c", "import gi; gi.require_version('Nautilus', '4.1'); from gi.repository import Nautilus"], capture_output=True)
    if check.returncode:
        raise ValueError("Install nautilus-python and python-gobject before installing this plugin.")
    subprocess.run(["omarchy", "plugin", "validate", str(ROOT)], check=True)
    if paths.plugin.exists() and paths.plugin.resolve() != ROOT:
        raise ValueError(f"Plugin directory already exists: {paths.plugin}. Update that checkout directly.")
    if paths.plugin.resolve() != ROOT:
        paths.plugin.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT, paths.plugin, ignore=shutil.ignore_patterns(".git", "__pycache__", "preview", ".pytest_cache"))
    apply(paths)
    subprocess.run(["omarchy-shell", "shell", "rescanPlugins"], check=True)
    subprocess.run(["omarchy", "plugin", "enable", PLUGIN_ID], check=True)
    print("Installed Oma File Explorer. Close Files and reopen it to load the styling extension.")
    print("If Files keeps running in the background, quit it after file transfers finish, then reopen it.")


def preview(theme, output):
    colors = palette(theme)
    css, icons = render(theme, fallback_theme(theme, "Adwaita"))
    # A preview owns a fresh directory, never replaces existing user content.
    output.mkdir(parents=True, exist_ok=False)
    atomic_write(output / "style.css", css)
    for relative, content in icons.items():
        atomic_write(output / "icons" / ICON_THEME / relative, content)
    tiles = []
    names = list(BADGES)[:12]
    for i, name in enumerate(names):
        x, y = 40 + (i % 6) * 150, 140 + (i // 6) * 136
        svg = icon_svg(colors, BADGES[name], name=name).replace('<svg ', f'<svg x="{x + 28}" y="{y}" ')
        label = name.removeprefix("folder-").removeprefix("user-").replace("publicshare", "shared").title()
        tiles.append(svg + f'<text x="{x + 60}" y="{y + 91}" text-anchor="middle" font-size="13">{label}</text>')
    symbols = []
    for i, name in enumerate(names):
        svg = icon_svg(colors, symbolic=True, name=name).replace('#bebebe', colors['foreground'])
        symbols.append(svg.replace('<svg ', f'<svg x="{40 + i * 36}" y="442" '))
    sheet = f'''<svg xmlns="http://www.w3.org/2000/svg" width="980" height="540" viewBox="0 0 980 540">
<rect width="980" height="540" fill="{colors['background']}"/>
<g fill="{colors['foreground']}" font-family="monospace">
<text x="40" y="55" font-size="26">Oma File Explorer</text>
<text x="40" y="87" font-size="14">Folder artwork · colors from your Omarchy theme</text>
{''.join(tiles)}
<text x="40" y="426" font-size="12">Sidebar · drawn separately at 16 pixels</text>
{''.join(symbols)}
<text x="40" y="507" font-size="12">Your familiar file explorer. Dressed for Omarchy.</text></g></svg>'''
    atomic_write(output / "folders.svg", sheet)
    print(f"Preview generated at {output}. Desktop settings were not changed.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Make Files match your Omarchy theme.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "apply", "restore", "status", "watch"):
        sub.add_parser(name)
    demo = sub.add_parser("preview")
    demo.add_argument("--theme", type=Path)
    demo.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    paths = Paths()
    try:
        if args.command == "preview":
            preview(args.theme or paths.theme(), args.output)
        elif args.command == "install":
            install(paths)
        elif args.command == "apply":
            apply(paths)
            print("Styling applied. The first use requires reopening Files to load its extension.")
        elif args.command == "restore":
            restore(paths)
            print("Styling restored. Automatic updates are paused; use apply to resume.")
        elif args.command == "status":
            state = load_state(paths)
            print(json.dumps({"installed": paths.plugin.exists(), "styling": "paused" if state.get("paused") else "applied" if state.get("owned") else "inactive", "icon_theme": settings_get(), "css": str(paths.css)}, indent=2))
        else:
            watch(paths)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Oma File Explorer: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
