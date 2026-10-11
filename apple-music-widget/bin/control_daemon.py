#!/usr/bin/env python3
"""
Apple Music control daemon for Omarchy (Quickshell shell + Chromium web app).

Owns the in-page control surface used by the center-island bar widget:
  * An HTTP bridge on 127.0.0.1:9299:
      GET /status
      GET /cmd/play-pause | /cmd/play | /cmd/pause | /cmd/next | /cmd/prev
      GET /cmd/shuffle | /cmd/repeat[?mode=all|one|off]
      GET /cmd/search[?term=...]   (SPA search, playback keeps running)
      GET /cmd/open
      GET /cmd/storefront          (move the app to the home storefront)
  * Playback commands go over MPRIS (org.mpris.MediaPlayer2.chromium.*).
  * Shuffle/repeat go via MusicKit JS on the page (exact modes, no blind clicks).
  * Search clicks the in-app Search button and types into the search field
    over the Chrome DevTools Protocol, so playback never stops. Fallback for
    older builds: a locale-aware navigation (does stop playback).
  * Storefront: navigations reuse the CURRENT storefront path (/be, /us, ...)
    so the app is never kicked to a foreign storefront. /cmd/storefront
    returns the app to the configured home storefront (STOREFRONT below).

Pure stdlib + PyGObject. Single instance enforced via a session bus name.
"""

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

import gi

gi.require_version("GObject", "2.0")
from gi.repository import Gio, GLib

CDP_PORT = 9222
HTTP_PORT = 9299
APP_URL_PREFIX = "https://music.apple.com"
STOREFRONT = "be"  # where the user stands; /cmd/storefront moves the app here
LAUNCHER = os.path.expanduser("~/.config/omarchy/applemusic/launch")
BUS_NAME = "org.omarchy.AppleMusicDaemon"

# ---------------------------------------------------------------------------
# Minimal RFC6455 websocket client (stdlib only) for the CDP bridge
# ---------------------------------------------------------------------------


class WebSocketClient:
    def __init__(self, host, port, path, timeout=6.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s:%d\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host, port, key)
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("no websocket handshake response")
            buf += chunk
        head = buf.split(b"\r\n\r\n", 1)[0]
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise ConnectionError("websocket handshake failed")
        self.buffer = buf.split(b"\r\n\r\n", 1)[1]
        self.sock.settimeout(timeout)

    def _read_exact(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("connection closed")
            self.buffer += chunk
        out, self.buffer = self.buffer[:n], self.buffer[n:]
        return out

    @staticmethod
    def _client_frame(opcode, payload, fin=True):
        header = bytearray()
        header.append((0x80 if fin else 0) | opcode)
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return bytes(header) + mask + masked

    def send_text(self, text):
        self.sock.sendall(self._client_frame(0x1, text.encode()))

    def _send_pong(self, payload):
        self.sock.sendall(self._client_frame(0xA, payload))

    def recv_message(self):
        """Next full message as bytes (assemble fragments, answer pings)."""
        parts = []
        while True:
            hdr = self._read_exact(2)
            fin = hdr[0] & 0x80
            opcode = hdr[0] & 0x0F
            masked = hdr[1] & 0x80
            n = hdr[1] & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read_exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read_exact(8))[0]
            payload = self._read_exact(n)
            if masked:
                mask = self._read_exact(4)
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x9:
                self._send_pong(payload)
                continue
            if opcode == 0x8:
                raise ConnectionError("closed by peer")
            if opcode in (0x1, 0x2, 0x0):
                parts.append(payload)
                if sum(len(p) for p in parts) > 4 * 1024 * 1024:
                    raise ConnectionError("message too large")
                if fin:
                    return b"".join(parts)
            # ignore other control opcodes


class Cdp:
    """Chrome DevTools Protocol bridge to the Apple Music page."""

    def __init__(self):
        self._lock = threading.Lock()
        self._ws = None
        self._target_key = None
        self._seq = 0

    def page_target(self):
        req = urllib.request.Request("http://127.0.0.1:%d/json" % CDP_PORT)
        with urllib.request.urlopen(req, timeout=2) as resp:
            targets = json.loads(resp.read().decode())
        for t in targets:
            if t.get("type") == "page" and t.get("url", "").startswith(APP_URL_PREFIX):
                return t["id"], t.get("webSocketDebuggerUrl")
        return None, None

    def _connect(self):
        target_id, ws_url = self.page_target()
        if not ws_url:
            raise ConnectionError(
                "apple music page not reachable via CDP (port %d)" % CDP_PORT)
        key = (target_id, ws_url)
        if self._ws and self._target_key == key:
            return
        if self._ws:
            try:
                self._ws.sock.close()
            except OSError:
                pass
            self._ws = None
        path = ws_url.split(":%d" % CDP_PORT, 1)[1] or "/"
        self._ws = WebSocketClient("127.0.0.1", CDP_PORT, path)
        self._target_key = key

    def call(self, method, params):
        """Raw CDP command; returns the 'result' dict or None on failure."""
        with self._lock:
            for attempt in (1, 2):
                try:
                    self._connect()
                    self._ws.sock.settimeout(5.0)
                    self._seq += 1
                    seq = self._seq
                    self._ws.send_text(json.dumps({"id": seq, "method": method, "params": params}))
                    deadline = time.time() + 6
                    while time.time() < deadline:
                        self._ws.sock.settimeout(max(0.2, deadline - time.time()))
                        raw = self._ws.recv_message().decode("utf-8", "replace")
                        if not raw.startswith("{"):
                            continue
                        data = json.loads(raw)
                        if data.get("id") != seq:
                            continue  # skip page events
                        if "error" in data:
                            raise RuntimeError("CDP error on %s: %s" % (method, data["error"]))
                        return data.get("result", {})
                    raise ConnectionError("no CDP response in time")
                except (OSError, ConnectionError, RuntimeError, ValueError):
                    self._ws = None
                    self._target_key = None
                    if attempt == 2:
                        return None
            return None

    def evaluate(self, expression, return_by_value=True):
        """Run JS in the page; return the JSON 'value' of the result, or None."""
        result = self.call("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": return_by_value,
            "awaitPromise": False,
        })
        if result is None:
            return None
        return result.get("result", {}).get("value")


STATE_JS = """
(() => {
  try {
    var k = window.MusicKit.getInstance();
    var sh = k.shuffleMode, rp = k.repeatMode;
    return JSON.stringify({
      shuffle: sh === undefined || sh === null ? 'unknown' : (sh === 0 ? 'off' : 'on'),
      repeat: rp === undefined || rp === null ? 'unknown'
              : (rp === 0 ? 'off' : rp === 1 ? 'one' : 'all')
    });
  } catch (e) {
    return JSON.stringify({shuffle: 'unknown', repeat: 'unknown'});
  }
})()
"""

SHUFFLE_SET_JS = """(() => {
  const k = window.MusicKit.getInstance();
  k.shuffleMode = %d;
  return String(k.shuffleMode);
})()"""

SHUFFLE_TOGGLE_JS = """(() => {
  const k = window.MusicKit.getInstance();
  k.shuffleMode = k.shuffleMode === 1 ? 0 : 1;
  return String(k.shuffleMode);
})()"""

REPEAT_SET_JS = """(() => {
  const k = window.MusicKit.getInstance();
  k.repeatMode = %d;
  return String(k.repeatMode);
})()"""

CLICK_SEARCH_JS = """(() => {
  const els = [...document.querySelectorAll('button, [role=button], amp-search a, a')];
  const pick = (re) => els.find(e => re.test(((e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('title') || '')).trim()));
  const el = pick(/search in (apple )?music/i) || pick(/^search(?:\\s|$)/i) || pick(/^search in library/i);
  if (el) { el.click(); return 'clicked'; }
  return 'not-found';
})()"""

SET_SEARCH_JS = """(() => {
  const inp = document.querySelector('input');
  if (!inp) return 'no-input';
  inp.focus();
  inp.value = TERM_PLACEHOLDER;
  inp.dispatchEvent(new Event('input', {bubbles: true}));
  return 'set';
})()"""


# ---------------------------------------------------------------------------
# MPRIS
# ---------------------------------------------------------------------------


class Player:
    def __init__(self):
        self.session = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.name = None

    def find(self):
        try:
            result = self.session.call_sync(
                "org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus", "ListNames", None, None,
                Gio.DBusCallFlags.NONE, -1, None)
            names = [str(n) for n in result[0]]
        except Exception:
            names = []
        match = [n for n in names if n.startswith("org.mpris.MediaPlayer2.chromium")]
        self.name = match[0] if match else None
        return self.name

    def scalar(self, prop):
        if not self.name and not self.find():
            return None
        try:
            res = self.session.call_sync(
                self.name, "/org/mpris/MediaPlayer2",
                "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant.new_tuple(
                    GLib.Variant.new_string("org.mpris.MediaPlayer2.Player"),
                    GLib.Variant.new_string(prop),
                ),
                None, Gio.DBusCallFlags.NONE, -1, None)
        except Exception:
            self.name = None
            return None
        try:
            boxed = GLib.Variant.get_child_value(res, 0)
            inner = GLib.Variant.get_child_value(boxed, 0)
            return GLib.Variant.unpack(inner)
        except Exception:
            return None

    def metadata(self):
        meta = self.scalar("Metadata")
        return meta if isinstance(meta, dict) else {}

    def playing(self):
        return self.scalar("PlaybackStatus") == "Playing"

    def command(self, method):
        if not self.name and not self.find():
            return False
        try:
            self.session.call_sync(
                self.name, "/org/mpris/MediaPlayer2",
                "org.mpris.MediaPlayer2.Player", method, None, None,
                Gio.DBusCallFlags.NONE, -1, None)
            return True
        except Exception:
            self.name = None
            return False


# ---------------------------------------------------------------------------
# Hyprland window helpers
# ---------------------------------------------------------------------------

TERMINAL_CLASSES = ("foot", "kitty", "alacritty", "ghostty", "org.gnome.terminal", "terminal")


def find_app_window():
    try:
        out = subprocess.run(["hyprctl", "-j", "clients"],
                             capture_output=True, timeout=5, text=True)
        clients = json.loads(out.stdout)
    except Exception:
        return None
    by_class, by_title = None, None
    for w in clients:
        cls = (w.get("class") or "").lower()
        title = (w.get("title") or "").lower()
        if "music.apple.com" in cls:
            by_class = w["address"]
            break
        if "apple music" in title and cls not in TERMINAL_CLASSES and not by_title:
            by_title = w["address"]
    return by_class or by_title


def open_app_window():
    addr = find_app_window()
    if addr:
        subprocess.run(["hyprctl", "dispatch", "focuswindow", "address:%s" % addr],
                       timeout=5, capture_output=True)
        return "focused"
    subprocess.Popen(["setsid", LAUNCHER],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "launched"


# ---------------------------------------------------------------------------
# Daemon state + actions
# ---------------------------------------------------------------------------


class Daemon:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {
            "cdp": False, "player": False, "playing": False,
            "title": "", "artist": "", "shuffle": "unknown", "repeat": "unknown",
        }
        self.player = Player()
        self.cdp = Cdp()
        self.quit_requested = False

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def poll_once(self):
        has_player = bool(self.player.name if self.player.name else self.player.find())
        playing = has_player and self.player.playing()
        meta = self.player.metadata() if has_player else {}
        title = str(meta.get("xesam:title") or "")
        artist = meta.get("xesam:artist") or ""
        if isinstance(artist, (list, tuple)):
            artist = ", ".join(str(a) for a in artist)
        artist = str(artist or "")

        cdp_ok = False
        raw = self.cdp.evaluate(STATE_JS)
        page = None
        if raw:
            try:
                page = json.loads(raw)
                cdp_ok = True
            except Exception:
                page = None

        new_state = {
            "player": has_player, "playing": playing, "title": title, "artist": artist,
            "cdp": cdp_ok,
            "shuffle": (page or {}).get("shuffle", self.state.get("shuffle", "unknown")),
            "repeat": (page or {}).get("repeat", self.state.get("repeat", "unknown")),
        }

        with self.lock:
            self.state.update(new_state)

    def poll_loop(self):
        while not self.quit_requested:
            try:
                self.poll_once()
            except Exception as e:
                print("poll error: %r" % e, file=sys.stderr)
            time.sleep(2)

    def set_shuffle(self, target):
        """target: 'on'/'off' or None to toggle."""
        if target in ("on", "off"):
            js = SHUFFLE_SET_JS % (1 if target == "on" else 0)
        else:
            js = SHUFFLE_TOGGLE_JS
        self.cdp.evaluate(js)
        self.prewarm_state()

    def set_repeat(self, mode):
        """Cycle repeat blindly, or steer to a specific mode ('off'|'all'|'one')."""
        modes = {"off": 0, "one": 1, "all": 2}
        if mode in modes:
            self.cdp.evaluate(REPEAT_SET_JS % modes[mode])
        else:
            current = self.state.get("repeat", "unknown")
            nxt = {"unknown": 2, "off": 2, "all": 1, "one": 0}.get(current, 0)
            self.cdp.evaluate(REPEAT_SET_JS % nxt)
        self.prewarm_state()

    def prewarm_state(self):
        try:
            self.poll_once()
        except Exception:
            pass

    def search(self, term):
        """Open in-app search and (optionally) type a query, keeping playback.

        The Apple Music web app is a SPA: clicking its Search button switches
        the view without a reload, and live results follow a value+input event
        on the search field. No page navigation, so playback never stops.
        Falls back to a locale-aware navigation only if the SPA path fails
        (that fallback does stop playback).
        """
        term = (term or "").strip()
        on_search = self.cdp.evaluate(
            "location.pathname.toLowerCase().indexOf('/search') !== -1")
        if not on_search:
            result = self.cdp.evaluate(CLICK_SEARCH_JS)
            if result == "clicked":
                time.sleep(0.8)
            else:
                self.navigate_to("", "/search"
                                 + (("?term=" + urllib.parse.quote(term)) if term else ""))
                return
        if term:
            js = SET_SEARCH_JS.replace("TERM_PLACEHOLDER", json.dumps(term))
            self.cdp.evaluate(js)

    def storefront(self):
        """Return the app to the home storefront (one page reload)."""
        self.navigate_to(STOREFRONT, "/home")

    def navigate_to(self, storefront, path):
        """Assign a locale-aware URL so we never land on a foreign storefront."""
        current = self.cdp.evaluate(
            "(() => { const m = location.pathname.split('/')[1] || ''; "
            "return /^[a-z]{2}$/.test(m) ? location.origin + '/' + m : ''; })()")
        base = current or (APP_URL_PREFIX + "/" + STOREFRONT)
        url = base + path
        self.cdp.evaluate("window.location.assign(%s)" % json.dumps(url))
        return url

    def do_action(self, action, extra=None):
        try:
            if action == "play-pause":
                self.player.command("PlayPause")
            elif action == "play":
                self.player.command("Play")
            elif action == "pause":
                self.player.command("Pause")
            elif action == "next":
                self.player.command("Next")
            elif action == "prev":
                self.player.command("Previous")
            elif action == "shuffle":
                self.set_shuffle(extra if extra in ("on", "off", None) else None)
            elif action == "repeat":
                self.set_repeat(extra if extra in ("off", "all", "one", None) else None)
            elif action == "search":
                self.search(extra or "")
                open_app_window()
            elif action == "open":
                open_app_window()
            elif action == "storefront":
                self.storefront()
        finally:
            for delay in (0.6, 0.9):
                time.sleep(delay)
                try:
                    self.poll_once()
                except Exception:
                    pass


def http_serve(daemon):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            parts = [p for p in parsed.path.split("/") if p]
            if parts == ["status"]:
                return self._json(daemon.snapshot())
            if parts[:2] == ["cmd", "search"]:
                qs = urllib.parse.parse_qs(parsed.query)
                daemon.do_action("search", qs.get("term", [""])[0])
                return self._json({"ok": True})
            if parts[0] == "cmd" and len(parts) == 2:
                action = parts[1].replace("-", "_")
                qs = urllib.parse.parse_qs(parsed.query)
                fn = {
                    "play_pause": lambda: daemon.do_action("play-pause"),
                    "play": lambda: daemon.do_action("play"),
                    "pause": lambda: daemon.do_action("pause"),
                    "next": lambda: daemon.do_action("next"),
                    "prev": lambda: daemon.do_action("prev"),
                    "open": lambda: daemon.do_action("open"),
                    "shuffle": lambda: daemon.do_action(
                        "shuffle", qs.get("state", [None])[0]),
                    "repeat": lambda: daemon.do_action(
                        "repeat", qs.get("mode", [None])[0]),
                    "storefront": lambda: daemon.do_action("storefront"),
                }.get(action)
                if not fn:
                    return self._json({"ok": False, "error": "unknown command"})
                fn()
                return self._json({"ok": True, "state": daemon.snapshot()})
            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), Handler)
    server.daemon_threads = True
    server.serve_forever()


def main():
    try:
        Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except Exception as e:
        print("no session bus: %r" % e, file=sys.stderr)
        return 1

    # single-instance guard
    owner = {"id": 0}

    def on_name_lost(conn, name):
        print("bus name lost (already running?) - exiting", flush=True)
        os._exit(0)

    owner["id"] = Gio.bus_own_name(
        Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.NONE,
        None, lambda c, n: print("apple-music control daemon ready", flush=True),
        on_name_lost)

    daemon = Daemon()
    threading.Thread(target=daemon.poll_loop, daemon=True).start()
    threading.Thread(target=http_serve, args=(daemon,), daemon=True).start()

    loop = GLib.MainLoop.new(None, False)
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())