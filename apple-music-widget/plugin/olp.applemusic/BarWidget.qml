import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "olp.applemusic"

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  function refresh() {
    if (panelLoader.item && panelLoader.item.refresh) panelLoader.item.refresh()
  }

  function togglePanel() {
    if (panelLoader.item && panelLoader.item.toggle) panelLoader.item.toggle()
  }

  // Shape contract for shell.summon/hide/toggle routing.
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() {
    if (panelLoader.item && panelLoader.item.openFromHotkey) panelLoader.item.openFromHotkey()
  }

  function close() {
    if (panelLoader.item && panelLoader.item.close) panelLoader.item.close()
  }

  // Forwarded so this widget can stand in for the panel as the bar's popout
  // identity.
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  // The note glyph is always shown; the panel hosts all Apple Music controls.
  visible: true
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  function service() {
    return root.bar && root.bar.shell ? root.bar.shell.serviceFor("olp.applemusic") : null
  }

  function appTooltip() {
    var svc = root.service()
    if (!svc || !svc.hasPlayer || !svc.title)
      return "Apple Music"
    return svc.title + (svc.artist !== "" ? " — " + svc.artist : "")
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰝚"
    slotSize: Style.bar.statusSlot
    tooltipText: root.appTooltip()

    onPressed: function(b) {
      if (b === Qt.RightButton) {
        var svc = root.service()
        if (svc) svc.runDaemonCmd("/cmd/open")
      } else if (b === Qt.MiddleButton) {
        var svc2 = root.service()
        if (svc2) svc2.togglePlay()
      } else {
        root.togglePanel()
      }
    }
  }
}