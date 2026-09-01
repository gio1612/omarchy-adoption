import QtQuick
import Quickshell
import Quickshell.Io

// Not an Omarchy-documented convention: a small JSON-lines client over
// Quickshell's own Socket/SplitParser types, talking to the tracker daemon's
// Unix socket.
//
// Reconnect policy: the daemon can legitimately be absent forever (the user
// added the plugin but never ran setup.sh), so the backoff has to *stop
// costing anything* in that state rather than retry at a fixed cadence. It
// grows 400ms -> 30s; at the cap an uninstalled daemon costs two socket
// objects a minute instead of ~200.
//
// In-flight requests: `pending` maps request id -> callback. It is mutated in
// place, and cleared on every disconnect. It used to be copy-on-write and was
// never cleared, so an unanswered request (socket died mid-flight) leaked its
// entry forever and every subsequent send copied the whole growing map --
// quadratic work on a timer, which is exactly what a long session felt like.
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
  property int lastLogTotal: 0
  property int reconnectAttempt: 0

  // Grows 400ms -> 30s. Capped attempt count keeps the exponent finite.
  readonly property int reconnectInterval: Math.min(
    30000, Math.round(400 * Math.pow(1.6, Math.min(root.reconnectAttempt, 12))))

  // A request whose answer never arrives (daemon killed mid-flight) must not
  // keep its callback alive forever.
  readonly property int requestTimeoutMs: 15000

  readonly property bool loggingEnabled: !!(lastStats && lastStats.logging_enabled)
  readonly property var activeSocket: socketLoader.item
  readonly property bool connected: !!(activeSocket && activeSocket.connected)

  property int nextId: 1
  property var pending: ({})
  property int pendingCount: 0

  readonly property string socketPath: {
    var runtime = Quickshell.env("XDG_RUNTIME_DIR")
    return String(runtime || "/tmp") + "/omarchy-adoption-tracker/daemon.sock"
  }

  signal statsReceived(var stats)
  signal historyReceived(var history)
  signal logReceived(var lines, int total)

  // ------------------------------------------------------------- requests

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
    if (typeof callback === "function") {
      pending[String(id)] = { callback: callback, sentAt: Date.now() }
      pendingCount++
    }
    socket.write(JSON.stringify(payload) + "\n")
    socket.flush()
    return id
  }

  function takePending(id) {
    var entry = pending[id]
    if (entry === undefined) return null
    delete pending[id]
    pendingCount = Math.max(0, pendingCount - 1)
    return entry
  }

  function resetPending(reason) {
    var ids = Object.keys(pending)
    for (var i = 0; i < ids.length; i++) {
      var entry = pending[ids[i]]
      delete pending[ids[i]]
      if (entry && typeof entry.callback === "function") {
        entry.callback(false, null, reason || "disconnected")
      }
    }
    pendingCount = 0
  }

  function reapStalePending() {
    if (pendingCount === 0) return
    var cutoff = Date.now() - root.requestTimeoutMs
    var ids = Object.keys(pending)
    for (var i = 0; i < ids.length; i++) {
      var entry = pending[ids[i]]
      if (!entry || entry.sentAt > cutoff) continue
      delete pending[ids[i]]
      pendingCount = Math.max(0, pendingCount - 1)
      if (typeof entry.callback === "function") entry.callback(false, null, "timed out")
    }
  }

  function requestStats(windowArg) {
    var w = windowArg || root.window
    sendCommand("stats", { window: w }, function(ok, result) {
      if (!ok || !result) return
      root.lastStats = result
      root.statsReceived(result)
    })
  }

  function requestRecords() {
    sendCommand("records", null, function(ok, result) {
      if (ok && result) root.lastRecords = result
    })
  }

  function requestHistory(days) {
    sendCommand("history", { days: days || 14 }, function(ok, result) {
      if (!ok || !result) return
      root.lastHistory = result
      root.historyReceived(result)
    })
  }

  function setLogging(enabled) {
    sendCommand("set_logging", { enabled: !!enabled }, function(ok, result) {
      if (!ok || !result) return
      root.lastStats = withLoggingFlag(root.lastStats, result.logging_enabled)
      if (!result.logging_enabled) {
        root.lastLog = []
        root.lastLogTotal = 0
      }
    })
  }

  // `limit` bounds how many audit lines come back. The panel polls this while
  // its Debug Audit view is open, so shipping the daemon's whole 400-line
  // ring every poll meant rebuilding a 400-item list once a second.
  function requestLog(limit) {
    sendCommand("get_log", { limit: limit || 120 }, function(ok, result) {
      if (!ok || !result) return
      root.lastStats = withLoggingFlag(root.lastStats, result.logging_enabled)
      var lines = result.lines || []
      // Replacing the array replaces every delegate downstream. Skip the
      // assignment when the content is unchanged, which is the common case
      // for a poll on an idle machine.
      if (!sameLines(root.lastLog, lines)) root.lastLog = lines
      root.lastLogTotal = Number(result.total || lines.length)
      root.logReceived(lines, root.lastLogTotal)
    })
  }

  function sameLines(a, b) {
    if (!a || !b || a.length !== b.length) return false
    for (var i = 0; i < a.length; i++) if (a[i] !== b[i]) return false
    return true
  }

  function withLoggingFlag(stats, enabled) {
    if (!stats || enabled === undefined || enabled === null) return stats
    var merged = ({})
    for (var key in stats) merged[key] = stats[key]
    merged.logging_enabled = enabled
    return merged
  }

  // ------------------------------------------------------------- receiving

  function handleLine(line) {
    var message = null
    try {
      message = JSON.parse(line)
    } catch (err) {
      return
    }
    if (!message || typeof message !== "object") return

    if (message.type === "event") {
      if (message.event === "stats_update" && message.state) {
        root.lastStats = message.state
        root.statsReceived(message.state)
      }
      return
    }
    if (message.type !== "response") return

    var entry = takePending(String(message.id === undefined ? "" : message.id))
    if (!entry || typeof entry.callback !== "function") return

    if (message.ok === true) entry.callback(true, message.result || ({}), "")
    else entry.callback(false, null, (message.error && message.error.message) || "request failed")
  }

  // ------------------------------------------------------------- lifecycle

  function tearDownSocket() {
    reconnectTimer.stop()
    socketLoader.active = false
    reconnectAttempt = 0
    resetPending("client stopped")
  }

  onWantedChanged: if (!wanted) tearDownSocket()

  onConnectedChanged: {
    if (!connected) {
      // Anything still in flight will never be answered by this socket.
      resetPending("daemon disconnected")
      return
    }
    reconnectAttempt = 0
    sendCommand("hello", null, null)
    root.requestStats(root.window)
  }

  Component.onDestruction: resetPending("client destroyed")

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

  // A failed connect leaves Quickshell's Socket holding a dead QLocalSocket,
  // and toggling Loader.active within one tick is a no-op -- so drop the
  // socket on one tick and open a new one on the next. `interval` is read
  // fresh on every restart, so the backoff really does widen.
  Timer {
    id: reconnectTimer
    interval: root.reconnectInterval
    repeat: true
    triggeredOnStart: true
    running: root.wanted && !root.connected
    onTriggered: {
      if (socketLoader.active) {
        socketLoader.active = false
        return
      }
      root.reconnectAttempt = Math.min(12, root.reconnectAttempt + 1)
      socketLoader.active = true
    }
  }

  Timer {
    interval: 5000
    repeat: true
    running: root.connected && root.pendingCount > 0
    onTriggered: root.reapStalePending()
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
