import QtQuick
import Quickshell.Io

Item {
    id: root
    property var manifest: null
    property var shell: null
    property var pluginRegistry: null
    property string omarchyPath: ""
    readonly property string pluginDir: manifest && manifest.__sourceDir ? String(manifest.__sourceDir) : ""

    Process {
        id: watcher
        command: ["python3", root.pluginDir + "/oma_file_explorer.py", "watch"]
        running: root.pluginDir !== ""
        stderr: StdioCollector {
            onStreamFinished: if (text.trim()) console.warn("Oma File Explorer: " + text.trim())
        }
    }
}
