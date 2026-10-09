"""Exercise the actual QML entry point with Omarchy's public manifest shape."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("quickshell"), "Quickshell is required for service integration tests")
class ServiceStartupTests(unittest.TestCase):
    def test_public_manifest_starts_watcher_in_encoded_directory(self):
        with tempfile.TemporaryDirectory(prefix="oma-service-") as temporary:
            root = Path(temporary)
            plugin = root / "plugin with spaces # café"
            plugin.mkdir()
            shutil.copyfile(ROOT / "Service.qml", plugin / "Service.qml")
            marker = root / "started.json"
            (plugin / "oma_file_explorer.py").write_text(
                "import json, os, pathlib, sys, time\n"
                "pathlib.Path(os.environ['OMA_TEST_MARKER']).write_text(json.dumps(sys.argv))\n"
                "print('startup-test-message', file=sys.stderr, flush=True)\n"
                "time.sleep(30)\n")
            # Omarchy strips its internal __sourceDir field for community plugins.
            (plugin / "shell.qml").write_text('''import QtQuick
import Quickshell
ShellRoot {
    Service {
        manifest: ({"id": "community.oma-file-explorer", "kinds": ["service"]})
    }
    Timer { interval: 1500; running: true; onTriggered: Qt.quit() }
}
''')
            runtime = root / "runtime"
            runtime.mkdir(mode=0o700)
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="basic",
                       QT_QUICK_CONTROLS_STYLE="Basic",
                       XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(root / "config"),
                       XDG_DATA_HOME=str(root / "data"), XDG_STATE_HOME=str(root / "state"),
                       XDG_CACHE_HOME=str(root / "cache"), OMA_TEST_MARKER=str(marker),
                       DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent-oma-test-bus")
            result = subprocess.run(["quickshell", "-p", str(plugin / "shell.qml")],
                                    env=env, capture_output=True, text=True, timeout=15)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertTrue(marker.exists(), output)
            self.assertEqual(json.loads(marker.read_text()), [str(plugin / "oma_file_explorer.py"), "watch"])
            self.assertIn("startup-test-message", output)


if __name__ == "__main__":
    unittest.main()
