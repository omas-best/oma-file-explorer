import QtQuick
import Quickshell.Io

Item {
    id: root
    property var manifest: null
    property var shell: null
    property var pluginRegistry: null
    property string omarchyPath: ""
    // Community manifests omit __sourceDir. Resolve next to this QML file,
    // including URL-encoded spaces and Unicode in the checkout path.
    readonly property string controlScript: decodeURIComponent(
        Qt.resolvedUrl("oma_file_explorer.py").toString().replace(/^file:\/\//, ""))

    Process {
        id: watcher
        command: ["python3", root.controlScript, "watch"]
        running: true
        stderr: SplitParser {
            onRead: function(line) {
                if (line.trim()) console.warn("Oma File Explorer: " + line.trim());
            }
        }
    }
}
