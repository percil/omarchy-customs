# Apple Music in the Omarchy center island

A bar widget and a small control service that turn the Apple Music **web
app** (a Chromium `--app` window) into a first-class Omarchy citizen: one
music-note icon in the top-middle island opens a popup with play/pause,
previous/next, **shuffle and repeat**, and an **in-app search** — all without
leaving the bar, and all without ever interrupting playback.

Done entirely through user-space customization; nothing under
`/usr/share/omarchy/` is touched, so `omarchy update` won't clobber it.

## Why this exists

The Apple Music web player only exposes play/pause/next/previous over
MPRIS (Chromium forwards what the Media Session API allows — shuffle and
repeat are simply not in that API). So this setup:

- uses **MPRIS for the transport controls** (play/pause, prev/next) via
  Quickshell's built-in `Quickshell.Services.Mpris`;
- controls **shuffle/repeat/search through the page itself** over the Chrome
  DevTools Protocol, driven by a tiny Python daemon the widget talks to;
- for search, the daemon **clicks the app's own Search button and types into
  its search field** (SPA navigation + live results) — the page never reloads,
  so **music keeps playing** while you search;
- keeps every URL navigation **locale-aware**: the daemon reuses whatever
  storefront the app is on (e.g. `/be` for Belgium) and can move the app back
  to the home storefront with one command.

The web app is otherwise a plain Chromium window: closing it quits the app
and the widget's controls dim (they reactivate the moment the app is back).

## What's installed where

This folder is a **snapshot + documentation** of the live setup, not the
live location itself. The actual files Omarchy loads are:

| Live path | Snapshot in this folder | Purpose |
|---|---|---|
| `~/.config/omarchy/plugins/olp.applemusic/` | `plugin/olp.applemusic/` | The shell plugin: `Service.qml` (MPRIS + daemon bridge + IPC), `BarWidget.qml` (the note icon in the center island), `Panel.qml` (the popup with all controls), `manifest.json`. |
| `~/.config/omarchy/applemusic/control_daemon.py` | `bin/control_daemon.py` | Python (stdlib + PyGObject) control service: owns CDP/MusicKit control, MPRIS dispatch, and an HTTP bridge on `127.0.0.1:9299`. Spawned and watched by `Service.qml`. Despite the historical name (`tray_daemon.py`), it no longer registers any tray item. |
| `~/.config/omarchy/applemusic/launch` | `bin/launch` | Chromium wrapper that launches the app with `--remote-debugging-port=9222` (localhost only — required for shuffle/repeat/search). |
| `~/.local/share/applications/Apple Music.desktop` | `desktop/Apple Music.desktop` | Desktop entry; `Exec` points at the launcher above instead of `omarchy-launch-webapp`. |
| `~/.local/share/icons/hicolor/256x256/apps/apple-music.png` | `icons/hicolor/256x256/apps/apple-music.png` | The app icon used by the desktop entry (created by whichever tool installed the web app; snapshotted here so the entry never goes iconless). |
| `~/.config/omarchy/shell.json` | *(edit, not a file in this snapshot)* | The bar layout: `{"id": "olp.applemusic"}` placed right after the clock entry in `bar.layout.center`. |

## How to use it

- **Center island**: a single note glyph (󰝚) sits right of the clock.
  - Left-click → popup: track art + title/artist/album, shuffle · previous ·
    play/pause · next · repeat, a search field (Enter or the 🔍 button
    commits), and an "Open Apple Music" button.
  - Shuffle/repeat buttons light up (accent color) while active; repeat cycles
    off → all → one.
  - Middle-click → play/pause. Right-click → focus the app window.
- **Keyboard/IPC**: `omarchy-shell applemusic <method>` from a keybinding:
  `status`, `playPause`, `next`, `previous`, `shuffle`, `repeat`,
  `search <term>`, `open`, `ping`. Example:
  `omarchy-shell applemusic search "duke ellington"`.
- **Daemon HTTP bridge** (for scripts): `curl 127.0.0.1:9299/status`,
  `.../cmd/play-pause`, `.../cmd/next`, `.../cmd/shuffle?state=on`,
  `.../cmd/repeat?mode=all`, `.../cmd/search?term=…`, `.../cmd/open`,
  `.../cmd/storefront` (moves the app back to the `STOREFRONT` constant at
  the top of the daemon — set it to your own region).
- The shell layout entry is edited in `~/.config/omarchy/shell.json`; the
  plugin itself is discovered automatically from `~/.config/omarchy/plugins/`.

## Reapply from this snapshot

```bash
# 1. Plugin
mkdir -p ~/.config/omarchy/plugins
cp -r plugin/olp.applemusic ~/.config/omarchy/plugins/

# 2. Control service + launcher
mkdir -p ~/.config/omarchy/applemusic
cp bin/control_daemon.py bin/launch ~/.config/omarchy/applemusic/
chmod +x ~/.config/omarchy/applemusic/launch

# 3. Desktop entry (adjust the Exec path if the home directory differs)
cp desktop/"Apple Music.desktop" ~/.local/share/applications/
sed -i "s|/home/olp|$HOME|" ~/.local/share/applications/"Apple Music.desktop"

# 4. Icon
mkdir -p ~/.local/share/icons/hicolor/256x256/apps
cp icons/hicolor/256x256/apps/apple-music.png ~/.local/share/icons/hicolor/256x256/apps/

# 5. Bar layout: put the widget right of the clock
#    Edit ~/.config/omarchy/shell.json and add to bar.layout.center:
#      { "id": "olp.applemusic" }
#    immediately after the clock entry (or: omarchy bar put olp.applemusic --after omarchy.clock).

# 6. Restart the shell, then (re)launch the Apple Music web app:
omarchy restart shell
```

You still need the web app itself installed (an `Apple Music` entry pointing
at `https://music.apple.com/`); on this machine it was created by Omarchy's
web-app installer and the snapshot only re-points its `Exec` at the launcher.

## Caveats worth knowing

- **The CDP port must be on the first Chromium start of the session.**
  Chromium delegates later `--app` launches to an already-running instance,
  ignoring their extra flags. If you open a *different* web app first, the
  Apple Music window joins it without CDP and the widget dims shuffle/repeat/
  search (transport controls keep working over MPRIS). Relaunching Apple
  Music alone doesn't help in that case — fully quit Chromium first
  (`pkill -f "chromium.*music.apple" | true; ~/.config/omarchy/applemusic/launch`).
- **Security posture**: `launch` exposes Chromium's DevTools protocol on
  `127.0.0.1:9222` (Chromium hard-restricts it to localhost). It's the
  standard mechanism, but be aware it lets any local process script that
  browser instance. The daemon's HTTP bridge is likewise localhost-only.
- **Storefront**: the daemon defaults `STOREFRONT = "be"` (Belgium) for
  fallback navigation and `/cmd/storefront`. Change it in
  `bin/control_daemon.py` (+ your live copy) if you're elsewhere.
- **Search is live-results**: the daemon types into the field and lets the
  app's as-you-type results show. It deliberately does *not* press Enter
  there — in this build, submitting the field reloads the page and stops
  playback.
- **Play/pause/next/previous only work while Chromium publishes a player**
  (which exists from the first played track until the app quits).
- The daemon is self-healing: `Service.qml` respawns it every 5 s if it dies.

## Troubleshooting

- Widget missing → `omarchy-shell shell rescanPlugins`, or
  `omarchy restart shell`; check the plugin is enabled: `omarchy shell list`.
- Shuffle/repeat/search dimmed → CDP offline; see the caveat above, then
  check `curl -s 127.0.0.1:9222/json | head` and
  `curl -s 127.0.0.1:9299/status`.
- Daemon not running → run it by hand to see why:
  `python3 ~/.config/omarchy/applemusic/control_daemon.py`
  (it exits immediately if already running — that's the single-instance
  guard, not an error).
- Shell QML errors → `journalctl --user | grep omarchy-shell`.