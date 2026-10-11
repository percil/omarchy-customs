# Devlog — Apple Music center-island widget

Chronological account of how this customization evolved. The README above is
the clean reference; this is the history.

## Round 1 — six buttons in the center island (2026-10-11, morning)

The request: Apple Music is installed as a web app; I want a widget in the
top-middle island to control it (play/pause/next/prev/shuffle/repeat), search
that redirects into the app, a tray-icon integration (left click reopens the
app, right click gives the controls) and minimize-to-tray.

Discovery:

- The app runs as `chromium --app=https://music.apple.com/` — a Chromium
  window launched via the desktop entry through `omarchy-launch-webapp`.
- Chromium publishes `org.mpris.MediaPlayer2.chromium.*` → play/pause/next/
  prev work. Verified **shuffle and loop are NOT reachable over MPRIS**
  (`Get` errors on both) — the Media Session API simply has no such actions.
- Omarchy's stock plugins include an `omarchy.media` widget, but it only
  surfaces what MPRIS gives; not enough for shuffle/repeat/search.

Approach A: inject clicks into the page via the Chrome DevTools Protocol
(CDP). That requires launching Chromium with `--remote-debugging-port`; I
wrapped the desktop entry's Exec in a `launch` script adding the flag for
Apple Music only.

Approach B (tray): Chromium web apps have no tray integration, so a
separate daemon registers a StatusNotifierItem + dbusmenu on the session
bus (PyGObject, stdlib only) and owns the CDP connection. Built as
`tray_daemon.py`; the bar widget (initially six always-visible buttons in
the island) and the tray both routed through its HTTP bridge
(127.0.0.1:9299).

Bugs found and fixed while building the daemon (each verified by
hand-crafted D-Bus calls):

- `Gio.DBusConnection.register_object()` takes no flags argument (PyGObject
  differs from the C API) — the daemon crash-looped invisibly until caught.
- `Properties.Get` must be called on the MPRIS object path itself, and only
  takes interface + property (I had passed the player's bus name three times
  — `GDBus.Error: ... error occurred in Get`).
- Registering with `org.kde.StatusNotifierWatcher` needs the item's **bus
  name**, not its object path.
- `GetGroupProperties` needs out-args wrapped in a *tuple* — returning the
  bare array stranded the caller for 25 s (dbus menu open feels hung).
- dbusmenu's label property is lowercase `"label"`; sending `"Label"` made
  Quickshell render a menu full of empty rows (user-reported).

Search v1: `location.assign('music.apple.com/search')` over CDP. Worked but
had two nasty side effects, reported by the user in round 3.

Verified working end-to-end: playback, shuffle on/off, repeat all/one/off
(read AND set — see the MusicKit discovery below), search redirect, tray
registration left/middle/right-click paths.

## Round 2 — redesign to a meteo-style popup (2026-10-11, afternoon)

User requests: the island should show a single note icon only (controls in a
click-popup like the weather widget, placed right of the clock), and the tray
menu rendered empty items (the `"label"` bug above).

Rewrote the widget following `panels/weather`: `BarWidget` (BarIconButton +
panel Loader, popout-coordination forwarding) + `Panel.qml` extending the
shell's `Ui.Panel` base with a `KeyboardPanel` popup: track art + title row,
transport row with accent-colored shuffle/repeat, search field, open button.
Also fixed: `Qt.binding()` used inside a binding declaration (invalid).

## Round 3 — search that keeps the music playing (2026-10-11, late)

User reports: searching opens a *brand new page*, logged out, suggesting
Belgium as home — and playback stops.

Root cause analysis on the live page:

1. `location.assign('https://music.apple.com/search')` — locale-less URL
   redirected to the **US storefront** (`/us/search`), logged out. Not
   actually a login loss: a different storefront view.
2. Pressing Enter in the search field makes the app navigate with
   `term=…` — also a **full page reload** → playback dies.

Key discoveries that shaped the fix:

- The player-bar components (`amp-playback-controls-shuffle/repeat`) use
  **closed shadow roots** → DOM clicking is a dead end.
- But the page embeds **MusicKit JS**. `window.MusicKit.getInstance()` has
  `shuffleMode` (0=off/1=on) and `repeatMode` (0=none/1=one/2=all) — exact,
  settable, readable. This is why round 1's "blind click + observe state"
  dance was replaced with direct property sets (also verified: Apple's UI
  buttons reflect programmatic changes).
- The search button (`Search in Apple Music`) and the search `<input>` are
  both **light DOM** → SPA search works: click the button (no reload), then
  `input.focus(); inp.value = term; dispatchEvent(new Event('input'))` →
  live results appear while music keeps playing (verified with a
  `window.__probe` marker surviving across the action, MPRIS still
  `Playing`, same track).
- Enter is deliberately *not* pressed (see README caveats).

Storefront fix: `navigate_to` reuses the current storefront prefix from
`location.pathname` (`/be`) and `/cmd/storefront` restores the app to
`music.apple.com/be/home` (verified logged in).

## Round 4 — archive + cleanup (2026-10-11, evening)

User: remove the now-redundant tray applet (controls live in the island
popup), archive this under `omarchy-customs`.

- Stripped SNI/dbusmenu from the daemon; renamed it `control_daemon.py`
  (a pure control service: MPRIS + CDP + HTTP bridge).
- Replaced the respawn `onExited → Timer` with a 5 s watchdog `Timer` in
  `Service.qml` (hot-reload races could kill the respawn path).
- Required `omarchy restart shell`: after a mid-session shell restart the
  plugin file watcher went stale — hot reloads claimed to process changes
  while actually serving stale code (fresh spawn of the renamed daemon
  didn't happen until a real restart).
- Snapshotted everything into this folder (role-structured), wrote the
  README/DEVLOG, updated the root index.

## Open issues

- None known. Degraded mode (no CDP) dims shuffle/repeat/search and is
  documented in the README.