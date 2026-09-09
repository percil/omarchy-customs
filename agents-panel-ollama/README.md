# Ollama in the Omarchy Agents panel

Adds Ollama as a third tab in Omarchy's built-in **Agents** bar widget
(`omarchy.agents` — the one that already shows Claude Code and Codex usage),
plus Start/Stop control over a local Ollama server. Done entirely through
user-space customization; nothing under `/usr/share/omarchy/` was touched, so
`omarchy update` won't clobber it.

## Why this exists

The Agents widget is display-only by design: it reads whatever `*.json`
usage records land in `~/.local/state/omarchy/agents/usage/`, one per agent,
written by `omarchy-agent-usage-<id>` collectors that ship in
`/usr/share/omarchy/bin/`. Claude and Codex have real rate-limit/usage APIs
to report; Ollama has no such API. So this integration:

- adds a **fourth, user-owned collector** (`omarchy-agent-usage-ollama`) that
  reports server up/down + installed models instead of quota;
- adds **Start/Stop/Refresh buttons** to the panel, which the stock widget
  never has (it's read-only by design) — Ollama runs as a plain local
  service you actually want to toggle, unlike a SaaS subscription;
- makes the Ollama tab **always visible**, even while stopped, so the
  controls are always reachable (the stock "hide the tab if there's nothing
  to show" rule doesn't fit a tab whose whole job is turning something on).

## What's installed where

This folder is a **snapshot + documentation** of the live setup, not the
live location itself. The actual files Omarchy/Quickshell load are:

| Live path | Snapshot in this folder | Purpose |
|---|---|---|
| `~/.config/omarchy/plugins/olp.agents/` | `plugin/olp.agents/` | Full clone of the stock `omarchy.agents` plugin (via `omarchy plugin clone omarchy.agents`), with Ollama support added. The bar (`~/.config/omarchy/shell.json`) points at `olp.agents` instead of the stock `omarchy.agents` since the clone. |
| `~/.local/bin/omarchy-agent-usage-ollama` | `bin/omarchy-agent-usage-ollama` | The Ollama status collector (bash + jq). Must be executable and on `PATH` (`~/.local/bin` already is). |
| `~/.config/systemd/user/ollama.service` | `systemd/user/ollama.service` | User-level systemd unit (`ExecStart=/usr/bin/ollama serve`). Created but left **disabled** — it's only ever started/stopped by hand or via the panel buttons, never at login. |

To restore/reapply from this snapshot on this or another machine:

```bash
mkdir -p ~/.config/omarchy/plugins ~/.local/bin ~/.config/systemd/user
cp -r plugin/olp.agents ~/.config/omarchy/plugins/
cp bin/omarchy-agent-usage-ollama ~/.local/bin/ && chmod +x ~/.local/bin/omarchy-agent-usage-ollama
cp systemd/user/ollama.service ~/.config/systemd/user/
systemctl --user daemon-reload
omarchy bar set omarchy.agents ... # not needed — shell.json already points at olp.agents once cloned
```

If starting fresh (no clone yet), run `omarchy plugin clone omarchy.agents`
first — that creates `~/.config/omarchy/plugins/<username>.agents/` and
switches the bar to it automatically — then overlay `plugin/olp.agents/`'s
contents onto it (the directory name will be `<username>.agents`, not
`olp.agents`, on a different account).

## How it works

### The collector: `bin/omarchy-agent-usage-ollama`

A small bash script, same contract as the stock `omarchy-agent-usage-claude`
/ `-codex` collectors (prints one JSON record to stdout), but written in
user space because `$OMARCHY_PATH/bin/` is packaged and off-limits for
end-user edits. It:

1. Checks whether Ollama is running — first by process match
   (`pgrep -f '(^|/)ollama serve$'`), then by systemd unit state — so it
   correctly detects a server started by hand in a terminal, not just one
   started through the unit below.
2. If running, lists installed models via `ollama list` (both local and
   `ollama.com` cloud-backed models — cloud models just show up in the same
   list with e.g. a `-cloud` tag suffix, like `gpt-oss:20b-cloud`).
3. Emits a record with `running`, `models`, `modelCount`, a human
   `usageStatusText` ("Running · 1 model" / "Stopped"), and
   `forceVisible: true`.

There is **no rate-limit or usage-quota data** in this record — Ollama
doesn't expose one via a public API (checked `ollama --help`; no
`usage`/`account`/`whoami` subcommand exists as of Ollama 0.33.3). The tab
intentionally shows status + models instead of pretending to have quota
numbers.

### Wiring it into the panel: `plugin/olp.agents/Main.qml`

Three targeted changes on top of the stock file:

1. **`runOllamaUpdate()`** — a new `Process` + function that runs the
   collector and writes `~/.local/state/omarchy/agents/usage/ollama.json`
   directly. Hooked into `runUpdate()` (called by the refresh timer, manual
   refresh, and limits-only refresh) so Ollama's record regenerates on the
   same cadence as Claude/Codex, without needing to touch
   `omarchy-agent-usage-update` (which only scans `$OMARCHY_PATH/bin/*`).
2. **`providerHasData(p)`** — added `|| p.forceVisible === true` so a record
   can opt into always showing its tab, regardless of usage numbers.
3. **`displayProvider(record)`** — passes through the Ollama-only fields
   (`running`, `serviceManaged`, `models`, `modelCount`, `forceVisible`);
   without this they'd be silently dropped when the raw record is normalized
   into the shape the panel renders.

### The panel UI: `plugin/olp.agents/Panel.qml`

- New **Ollama section** at the *bottom* of the panel column (below the
  Claude Code / Codex / Ollama tab switcher, which stays at the top like the
  stock layout): a "MODELS" list, then a row of three buttons — **Start
  Ollama**, **Stop Ollama**, **Refresh**.
- Two independent buttons rather than one label that toggles, because Ollama
  is just as often started by hand from a terminal — the panel shouldn't
  assume it's the only thing that can start or stop it. Start always goes
  through `systemctl --user start ollama.service` (a harmless no-op if
  something already holds the port). Stop stops the unit *and*
  `pkill -f 'ollama serve'`, so it works whether Ollama is running via the
  unit or was launched by hand.
- After either button, a short settle timer (600ms) re-runs the collector so
  the panel reflects the new state without waiting for the next scheduled
  refresh.
- Fixed the panel's "auth/error" banner (styled in the alarm/red color),
  which needed two rounds to get right:
  - Round 1: it was keyed on `usageStatusText` alone being non-empty, which
    is a safe-looking but wrong proxy — Ollama's record sets that field
    unconditionally as a normal status label ("Running"/"Stopped"), so it
    drew the banner empty on every refresh.
  - Round 2: re-keying on `authHelpText` alone (the field the banner
    actually renders) fixed Ollama but broke Claude/Codex the other way —
    both stock collectors default `authHelpText` to a static "run login"
    string and never clear it back to `""` on success, so it's non-empty
    almost all the time, success included, which lit the banner
    permanently for Claude/Codex.
  - Fix: the banner now requires **both** `usageStatusText` and
    `authHelpText` non-empty. Claude/Codex only ever set both together on a
    real error/waiting state; Ollama never sets `authHelpText` at all — so
    this is correct for every provider without special-casing any of them.

### Icon: `plugin/olp.agents/assets/ollama.svg` / `ollama-light.svg`

No bundled Ollama mark exists anywhere on this system (checked icon themes
and `/usr/share`), so this is a small original abstract mark (not a trace of
Ollama's actual logo), following the existing asset convention: `ollama.svg`
(white fill) shown on dark hero surfaces, `ollama-light.svg` (dark fill) on
light ones — same pattern as `codex.svg` / `codex-light.svg`.

## Known limitations / things to revisit

- No usage/rate-limit data for Ollama — by design, not a bug, until Ollama
  ships a public API for it.
- The Start/Stop buttons don't disable themselves based on state (clicking
  Start while already running, or Stop while already stopped, is just a
  harmless no-op) — kept simple on purpose.
- `ollama.service` (user unit) is not enabled at login; it only runs when
  started by hand or via the panel.
- This whole integration lives outside git — it's plain files in
  `~/.config` / `~/.local`. This folder is the durable record of what
  changed and why.

## Testing performed

- Verified the collector's JSON output directly, both running and stopped.
- Verified `systemctl --user start/stop ollama.service` actually starts and
  stops the server (checked `ss -ltnp` on port 11434 and `pgrep`).
- Reloaded the shell (`omarchy restart shell`) after each change and checked
  `journalctl` for the running Quickshell PID for QML warnings/errors —
  none found.
- Screenshotted the panel (via `omarchy capture screenshot fullscreen save`)
  at each stage to confirm the tab appears, stays visible while stopped, the
  buttons render and work, and the stray red banner is gone.
- For the `usageStatusText && authHelpText` banner fix: read the packaged
  Claude/Codex collector source to confirm the root cause, reloaded the
  shell and checked `journalctl --user` for QML warnings/errors (none), and
  cross-checked the new condition against the live
  `~/.local/state/omarchy/agents/usage/*.json` records for every provider
  (including `fireworks.json`, whose genuine auth error is unaffected).
