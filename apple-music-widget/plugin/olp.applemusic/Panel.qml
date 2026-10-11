import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "olp.applemusic"
  ipcTarget: ""
  manageIpc: false

  property var anchorItem: null
  property bool openedFromHotkey: false
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  readonly property var svc: bar && bar.shell ? bar.shell.serviceFor("olp.applemusic") : null
  readonly property bool hasPlayer: svc ? svc.hasPlayer : false
  readonly property bool playing: svc ? svc.isPlaying : false
  readonly property bool cdpAvailable: svc ? svc.cdpAvailable : false
  readonly property string title: svc ? (svc.title || "") : ""
  readonly property string artist: svc ? (svc.artist || "") : ""
  readonly property string album: svc ? (svc.album || "") : ""
  readonly property string artUrl: svc ? (svc.artUrl || "") : ""
  readonly property string shuffleState: svc ? svc.shuffleState : "unknown"
  readonly property string repeatState: svc ? svc.repeatState : "unknown"

  function open() {
    openedFromHotkey = false
    setCenterHoverRevealSuppressed(false)
    root.controller.show()
    root.refresh()
  }

  function openFromHotkey() {
    openedFromHotkey = true
    root.controller.show()
    root.refresh()
    Qt.callLater(function() {
      if (root.opened) setCenterHoverRevealSuppressed(true)
    })
  }

  function close() {
    setCenterHoverRevealSuppressed(false)
    searchField.focus = false
    root.controller.hide()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.openFromHotkey()
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function setCenterHoverRevealSuppressed(value) {
    if (root.bar && typeof root.bar.setCenterHoverRevealSuppressed === "function")
      root.bar.setCenterHoverRevealSuppressed(value)
    else if (root.bar && "centerHoverRevealSuppressed" in root.bar)
      root.bar.centerHoverRevealSuppressed = value
  }

  function refresh() {
    if (root.svc) root.svc.refreshDaemonStatus()
  }

  function act(action) {
    if (!root.svc) return
    if (action === "next") root.svc.next()
    else if (action === "previous") root.svc.previous()
    else if (action === "playPause") root.svc.togglePlay()
    else if (action === "shuffle") root.svc.runDaemonCmd("/cmd/shuffle")
    else if (action === "repeat") root.svc.runDaemonCmd("/cmd/repeat")
    else if (action === "open") root.svc.runDaemonCmd("/cmd/open")
  }

  function commitSearch() {
    var term = searchField.text.trim()
    if (!root.svc) return
    root.svc.runDaemonCmd("/cmd/search" + (term !== "" ? "?term=" + encodeURIComponent(term) : ""))
    root.close()
  }

  function returnFocusToKeyCatcher() {
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(400))
    contentHeight: panel.fittedContentHeight(contentCol.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: searchField.activeFocus
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: contentCol
        width: parent.width
        spacing: Style.space(12)

        // ---- Track info: art + title / artist / album
        Row {
          spacing: Style.space(10)
          width: parent.width

          BorderSurface {
            width: Style.space(64)
            height: Style.space(64)
            radius: Style.spacing.labelGap
            color: Style.normalFillFor(root.barForeground, Color.accent)
            borderSpec: Border.controlSpec("normal", root.barForeground, Color.accent)

            Image {
              anchors.fill: parent
              anchors.margins: Style.space(2)
              fillMode: Image.PreserveAspectCrop
              asynchronous: true
              source: root.artUrl
              visible: source !== ""
            }

            Text {
              anchors.centerIn: parent
              visible: root.artUrl === ""
              text: "󰝚"
              color: root.barForeground
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.displayLarge
            }
          }

          Column {
            spacing: Style.space(4)
            width: parent.width - Style.space(74)

            Text {
              textFormat: Text.PlainText
              text: root.title || "Not playing"
              color: root.bar.foreground
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.subtitle
              font.bold: true
              elide: Text.ElideRight
              width: parent.width
            }

            Text {
              textFormat: Text.PlainText
              text: root.artist
              color: Qt.darker(root.bar.foreground, 1.3)
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.bodySmall
              elide: Text.ElideRight
              width: parent.width
              visible: text !== ""
            }

            Text {
              textFormat: Text.PlainText
              text: root.album
              color: Qt.darker(root.bar.foreground, 1.6)
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.caption
              elide: Text.ElideRight
              width: parent.width
              visible: text !== ""
            }
          }
        }

        // ---- Playback controls: shuffle, prev, play/pause, next, repeat
        Row {
          anchors.horizontalCenter: parent.horizontalCenter
          spacing: Style.space(6)

          Button {
            iconText: "󰒉"
            foreground: root.shuffleState === "on" ? Color.accent : root.bar.foreground
            tooltipText: "Shuffle (" + root.shuffleState + ")"
            horizontalPadding: Style.spacing.controlPaddingX
            verticalPadding: Style.spacing.controlPaddingY
            enabled: root.cdpAvailable
            opacity: enabled ? 1.0 : 0.4
            onClicked: root.act("shuffle")
          }

          Button {
            iconText: "󰒮"
            foreground: root.bar.foreground
            horizontalPadding: Style.spacing.controlPaddingX
            verticalPadding: Style.spacing.controlPaddingY
            enabled: root.hasPlayer
            opacity: enabled ? 1.0 : 0.4
            onClicked: root.act("previous")
          }

          Button {
            iconText: root.playing ? "󰏤" : "󰐊"
            foreground: root.bar.foreground
            horizontalPadding: Style.spacing.panelGap
            verticalPadding: Style.spacing.controlPaddingY
            iconSize: Style.font.iconLarge
            enabled: root.hasPlayer
            opacity: enabled ? 1.0 : 0.4
            onClicked: root.act("playPause")
          }

          Button {
            iconText: "󰒭"
            foreground: root.bar.foreground
            horizontalPadding: Style.spacing.controlPaddingX
            verticalPadding: Style.spacing.controlPaddingY
            enabled: root.hasPlayer
            opacity: enabled ? 1.0 : 0.4
            onClicked: root.act("next")
          }

          Button {
            iconText: "󰑖"
            foreground: root.repeatState === "off" || root.repeatState === "unknown" ? root.bar.foreground : Color.accent
            tooltipText: "Repeat (" + root.repeatState + ")"
            horizontalPadding: Style.spacing.controlPaddingX
            verticalPadding: Style.spacing.controlPaddingY
            enabled: root.cdpAvailable
            opacity: enabled ? 1.0 : 0.4
            onClicked: root.act("repeat")
          }
        }

        PanelSeparator {
          foreground: root.bar.foreground
        }

        // ---- Search row
        Row {
          spacing: Style.space(8)
          width: parent.width

          TextField {
            id: searchField
            width: parent.width - Style.space(46)
            placeholderText: root.cdpAvailable ? "Search Apple Music" : "Search unavailable (app offline)"
            foreground: root.bar.foreground
            font.family: root.bar.fontFamily
            enabled: root.cdpAvailable

            Keys.onPressed: function(event) {
              if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                root.commitSearch()
                event.accepted = true
              } else if (event.key === Qt.Key_Escape) {
                root.close()
                event.accepted = true
              }
            }
          }

          Button {
            iconText: "󰍉"
            foreground: root.bar.foreground
            enabled: root.cdpAvailable
            opacity: enabled ? 1.0 : 0.4
            verticalPadding: Style.spacing.controlPaddingY
            onClicked: root.commitSearch()
          }
        }

        Text {
          visible: !root.cdpAvailable
          text: "Relaunch Apple Music to enable shuffle, repeat and search."
          color: Qt.darker(root.bar.foreground, 1.5)
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
          font.italic: true
          wrapMode: Text.WordWrap
          width: parent.width
        }

        // ---- Open app row
        Button {
          anchors.horizontalCenter: parent.horizontalCenter
          text: "Open Apple Music"
          foreground: root.bar.foreground
          horizontalPadding: Style.spacing.controlPaddingX
          verticalPadding: Style.spacing.controlPaddingY
          onClicked: {
            root.act("open")
            root.close()
          }
        }
      }
    }
  }
}