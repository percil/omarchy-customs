import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Mpris

Item {
  id: root

  property var shell: null

  // ------------------------------------------------------------------ MPRIS
  readonly property var players: Mpris.players ? Mpris.players.values : []
  readonly property var applePlayer: {
    var found = null
    for (var i = 0; i < players.length; i++) {
      var p = players[i]
      var id = ((p && p.identity) || "").toLowerCase()
      if (id.indexOf("chromium") !== -1) {
        found = p
        break
      }
    }
    return found
  }
  readonly property bool hasPlayer: applePlayer !== null
  readonly property bool isPlaying: applePlayer ? applePlayer.isPlaying : false
  readonly property string title: applePlayer ? (applePlayer.trackTitle || "") : ""
  readonly property string artist: applePlayer ? (applePlayer.trackArtist || "") : ""
  readonly property string album: applePlayer && applePlayer.trackAlbum ? applePlayer.trackAlbum : ""
  readonly property string artUrl: applePlayer && applePlayer.trackArtUrl ? applePlayer.trackArtUrl : ""

  // ------------------------------------------------------- daemon HTTP bridge
  readonly property string daemonBase: "http://127.0.0.1:9299"
  readonly property string daemonScript: Quickshell.env("HOME") + "/.config/omarchy/applemusic/control_daemon.py"

  property var daemonState: ({})
  readonly property string shuffleState: daemonState.shuffle || "unknown"
  readonly property string repeatState: daemonState.repeat || "unknown"
  readonly property bool cdpAvailable: daemonState.cdp === true

  function togglePlay() {
    if (!applePlayer)
      return
    if (applePlayer.isPlaying && applePlayer.canPause)
      applePlayer.pause()
    else if (applePlayer.canPlay)
      applePlayer.play()
    else if (applePlayer.canTogglePlaying)
      applePlayer.togglePlaying()
  }

  function next() {
    if (applePlayer && applePlayer.canGoNext)
      applePlayer.next()
  }

  function previous() {
    if (applePlayer && applePlayer.canGoPrevious)
      applePlayer.previous()
  }

  // Generic one-shot daemon call. Writes the fresh /status-derived state
  // into daemonState so the widget buttons re-highlight immediately.
  Process {
    id: cmdProc
    stdout: StdioCollector {
      onStreamFinished: root.applyDaemonJson(text)
    }
  }

  Process {
    id: statusProc
    command: ["curl", "-s", "--max-time", "2", root.daemonBase + "/status"]
    stdout: StdioCollector {
      onStreamFinished: root.applyDaemonJson(text)
    }
  }

  function applyDaemonJson(raw) {
    var txt = String(raw || "").trim()
    if (txt === "")
      return
    try {
      var obj = JSON.parse(txt)
      var state = obj && obj.state ? obj.state : obj
      if (state && typeof state === "object") {
        root.daemonState = state
        if (state.shuffle === undefined)
          return
      }
    } catch (e) {
      // daemon down or malformed reply; leave state as-is
    }
  }

  function runDaemonCmd(path) {
    if (cmdProc.running)
      return
    cmdProc.command = ["curl", "-s", "--max-time", "4", root.daemonBase + path]
    cmdProc.running = true
  }

  function refreshDaemonStatus() {
    if (!statusProc.running)
      statusProc.running = true
  }

  Timer {
    interval: 3000
    running: true
    repeat: true
    onTriggered: root.refreshDaemonStatus()
  }

  onDaemonStateChanged: refreshIfVisible()

  function refreshIfVisible() {
    // no-op hook; state is read reactively by the widget
  }

  // ------------------------------------------------------------ tray daemon
  Process {
    id: trayProc
    command: ["python3", root.daemonScript]
    environment: {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  }

  // Watchdog: keep the daemon alive regardless of how it dies (crash, kill,
  // or a missed exit callback during plugin hot-reloads).
  Timer {
    interval: 5000
    running: true
    repeat: true
    onTriggered: if (!trayProc.running) trayProc.running = true
  }

  // -------------------------------------------------------------------- IPC
  IpcHandler {
    target: "applemusic"

    function status(): string {
      return JSON.stringify({
        "hasPlayer": root.hasPlayer,
        "playing": root.isPlaying,
        "title": root.title,
        "artist": root.artist,
        "shuffle": root.shuffleState,
        "repeat": root.repeatState,
        "cdp": root.cdpAvailable
      })
    }

    function playPause(): string {
      root.togglePlay()
      return "ok"
    }

    function next(): string {
      root.next()
      return "ok"
    }

    function previous(): string {
      root.previous()
      return "ok"
    }

    function shuffle(): string {
      root.runDaemonCmd("/cmd/shuffle")
      return "ok"
    }

    function repeat(): string {
      root.runDaemonCmd("/cmd/repeat")
      return "ok"
    }

    function search(args: string): string {
      var term = String(args || "").trim()
      root.runDaemonCmd("/cmd/search" + (term !== "" ? "?term=" + encodeURIComponent(term) : ""))
      return "ok"
    }

    function open(): string {
      root.runDaemonCmd("/cmd/open")
      return "ok"
    }

    function ping(): string {
      return "ok"
    }
  }

  Component.onCompleted: trayProc.running = true
}