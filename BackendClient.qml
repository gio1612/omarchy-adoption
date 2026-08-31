import QtQuick
import Quickshell
import Quickshell.Io

// Not an Omarchy-documented convention: a small JSON-lines client over
// Quickshell's own Socket/SplitParser types, talking to the tracker daemon's
// Unix socket. Reconnects with backoff since the daemon can legitimately be
// down (not yet installed) or mid-restart (systemd Restart=on-failure).
Item {
  id: root

  visible: false
  width: 0
  height: 0

  property bool wanted: true
  property string window: "today"
  property var lastStats: null
  property var lastRecords: null
  property var lastHistory: null
  property var lastLog: []
  property int reconnectAttempt: 0

  readonly property bool loggingEnabled: !!(lastStats && lastStats.logging_enabled)
  readonly property var activeSocket: socketLoader.item
  readonly property bool connected: !!(activeSocket && activeSocket.connected)

  property int nextId: 1
  property var pending: ({})

  readonly property string socketPath: {
    var runtime = Quickshell.env("XDG_RUNTIME_DIR")
    return String(runtime || "/tmp") + "/omarchy-adoption-tracker/daemon.sock"
  }

  signal statsReceived(var stats)
  signal historyReceived(var history)

  function sendCommand(name, fields, callback) {
    var socket = activeSocket
    if (!socket || !socket.connected) {
      if (typeof callback === "function") callback(false, null, "not connected")
      return 0
    }
    var id = nextId++
    var payload = { v: 1, id: id, command: String(name || "") }
    if (fields) {
      for (var key in fields) payload[key] = fields[key]
    }
    var nextPending = ({})
    for (var existing in pending) nextPending[existing] = pending[existing]
    nextPending[String(id)] = typeof callback === "function" ? callback : null
    pending = nextPending
    socket.write(JSON.stringify(payload) + "\n")
    socket.flush()
    return id
  }

  function requestStats(windowArg) {
    var w = windowArg || root.window
    sendCommand("stats", { window: w }, function(ok, result) {
      if (ok && result) {
        root.lastStats = result
        root.statsReceived(result)
      }
    })
  }

  function requestRecords() {
    sendCommand("records", null, function(ok, result) {
      if (ok && result) root.lastRecords = result
    })
  }

  function requestHistory(days) {
    sendCommand("history", { days: days || 14 }, function(ok, result) {
      if (ok && result) {
        root.lastHistory = result
        root.historyReceived(result)
      }
    })
  }

  function setLogging(enabled) {
    sendCommand("set_logging", { enabled: !!enabled }, function(ok, result) {
      if (ok && result) {
        root.lastStats = incrementLoggingFlag(root.lastStats, result.logging_enabled)
      }
    })
  }

  function requestLog(callback) {
    sendCommand("get_log", null, function(ok, result) {
      if (ok && result) {
        root.lastStats = incrementLoggingFlag(root.lastStats, result.logging_enabled)
        root.lastLog = result.lines || []
        if (typeof callback === "function") callback(result.lines || [])
      } else if (typeof callback === "function") {
        root.lastLog = []
        callback([])
      }
    })
  }

  function incrementLoggingFlag(stats, enabled) {
    if (stats && enabled !== undefined && enabled !== null) {
      var merged = ({})
      for (var key in stats) merged[key] = stats[key]
      merged.logging_enabled = enabled
      return merged
    }
    return stats
  }

  function handleLine(line) {
    var message = null
    try {
      message = JSON.parse(line)
    } catch (err) {
      return
    }
    if (!message || typeof message !== "object") return

    if (message.type === "event" && message.event === "stats_update" && message.state) {
      root.lastStats = message.state
      root.statsReceived(message.state)
      return
    }
    if (message.type !== "response") return

    var id = String(message.id || "")
    var callback = pending[id]
    if (callback === undefined) return
    var nextPending = ({})
    for (var key in pending) if (key !== id) nextPending[key] = pending[key]
    pending = nextPending
    if (typeof callback !== "function") return

    if (message.ok === true) callback(true, message.result || ({}), "")
    else callback(false, null, (message.error && message.error.message) || "request failed")
  }

  function tearDownSocket() {
    reconnectTimer.stop()
    socketLoader.active = false
    reconnectAttempt = 0
  }

  onWantedChanged: if (!wanted) tearDownSocket()

  onConnectedChanged: {
    if (!connected) return
    reconnectAttempt = 0
    sendCommand("hello", null, null)
    root.requestStats(root.window)
  }

  Component {
    id: socketComponent
    Socket {
      id: socket
      path: root.socketPath
      connected: false
      parser: SplitParser {
        splitMarker: "\n"
        onRead: function(line) { root.handleLine(line) }
      }
      Component.onCompleted: connected = true
      onError: function() { connected = false }
    }
  }

  Loader {
    id: socketLoader
    active: false
    sourceComponent: socketComponent
  }

  // A failed connect can leave a dead socket behind; drop it on one tick and
  // open a new one on the next, backing off as attempts accumulate.
  Timer {
    id: reconnectTimer
    interval: Math.min(5000, 300 + root.reconnectAttempt * 400)
    repeat: true
    triggeredOnStart: true
    running: root.wanted && !root.connected
    onTriggered: {
      root.reconnectAttempt = Math.min(20, root.reconnectAttempt + 1)
      if (socketLoader.active) {
        socketLoader.active = false
        return
      }
      socketLoader.active = true
    }
  }

  // Safety-net resync: the daemon pushes stats_update on every change, this
  // just guards against a dropped push.
  Timer {
    interval: 60000
    running: root.connected
    repeat: true
    onTriggered: root.requestStats(root.window)
  }
}
