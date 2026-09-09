# Dev log

Chronological record of how this feature came together, for context the
README doesn't carry.

## 1. Initial request

> Add ollama in the exposed systems in the top left "applet" (with Claude
> Code and Codex). Ollama is connected with my account and is able to deal
> with cloud models. Also add a button to "start/stop" ollama.

Investigation before writing anything:

- The "applet with Claude Code and Codex" is Omarchy's built-in **Agents**
  bar widget (`omarchy.agents`, in `/usr/share/omarchy/shell/plugins/agents/`
  — `Main.qml`, `Panel.qml`, `Agent.qml`, plus per-agent SVG marks).
- It's explicitly documented as **display-only**: it watches JSON records in
  `~/.local/state/omarchy/agents/usage/`, one per agent, produced by
  `omarchy-agent-usage-<id>` collectors shipped in `$OMARCHY_PATH/bin/`
  (read-only territory — never to be edited directly).
- Checked whether Ollama exposes any usage/rate-limit API the way Claude
  (OAuth usage endpoint) and Codex (app-server RPC) do: it doesn't.
  `ollama --help` has no `usage`/`account`/`whoami`. So a Claude/Codex-style
  quota tab isn't possible — decided early to show status + installed
  models instead, and say so plainly rather than fabricate numbers.
- Checked how Ollama was actually running on this machine: **not** via the
  packaged `ollama.service` (system-level, disabled, inactive) — it was a
  plain `ollama serve` process started by hand in a terminal, running as the
  user. That ruled out needing `pkexec`/sudo for the start/stop button: a
  user-level systemd unit is enough, no privilege escalation involved.
- Confirmed cloud-model connectivity: `ollama list` already showed
  `gpt-oss:20b-cloud` pulled and working.

Built:

- Cloned `omarchy.agents` → `~/.config/omarchy/plugins/olp.agents/` (bar
  auto-switched to it).
- Added `~/.local/bin/omarchy-agent-usage-ollama` (status + models
  collector).
- Added `~/.config/systemd/user/ollama.service` (created, left disabled —
  doesn't touch the already-running manual process until asked to).
- Added `assets/ollama.svg` / `ollama-light.svg` (original mark, since none
  existed anywhere on the system to reuse).
- Edited the cloned `Main.qml`: new `runOllamaUpdate()` riding the existing
  refresh cadence, `providerHasData()`/`displayProvider()` extended to carry
  Ollama's fields through.
- Edited the cloned `Panel.qml`: Ollama tab with a single toggling
  Start/Stop button, a Refresh button, and a models list.
- Verified end-to-end: reloaded the shell, watched `journalctl` for QML
  errors (none), screenshotted the panel, and exercised the actual
  `systemctl --user start/stop` commands to confirm the server really
  starts and stops.

## 2. Follow-up: separate Start button, always-visible tab

> Add a start button as well. ollama was running from a console. Also, I
> need it to be displayed all the time (the ollama section).

Two distinct fixes:

- **Single toggle → two independent buttons.** The user pointed out Ollama
  is often started by hand from a console, not only through the panel — a
  toggle button that assumes it owns the on/off state doesn't fit that. Split
  into `startOllama()` / `stopOllama()`, both always visible: Start is an
  idempotent `systemctl --user start` (safe no-op if already running from
  anywhere), Stop stops the unit *and* `pkill`s a manually-started process.
- **Tab disappearing while stopped.** Root cause: `providerHasData()` (the
  gate that decides whether a provider earns a tab at all) required some
  form of usage — prompts, sessions, active days, limits, or a balance.
  Ollama had none of those, and when stopped it also had `modelCount: 0`, so
  the whole tab collapsed out of the bar exactly when you'd want the Start
  button most. Fixed by adding a `forceVisible: true` flag the collector
  always sets, and a matching `|| p.forceVisible === true` clause in
  `providerHasData()` — generic, not Ollama-specific, so any future
  always-on agent can opt in the same way.

Verified by stopping Ollama, reloading the shell, and confirming the tab
(with Start/Stop/Refresh) stayed visible and correct while stopped.

## 3. Follow-up: layout order + the empty red box

> Invert the buttons (Claude Code, Codex, and Ollama must remain at the top
> while the control buttons from Ollama must be at the bottom). And what is
> the red rectangle for?

- **Layout.** The Ollama controls/models block had been inserted *above*
  the provider tab switcher (right after the hero), which pushed
  Claude Code / Codex / Ollama down and put Start/Stop up top — not what a
  user expects from a tab bar. Moved the whole block down to just above the
  footer, after the tokens-by-model section, so the tab switcher sits
  directly under the hero for every provider, same as stock.
- **The red box.** Turned out to be a real, if latent, bug: the panel's
  auth-error banner (alarm-red background) shows whenever
  `usageStatusText` is non-empty, and separately renders whatever is in
  `authHelpText`. For Claude/Codex those two fields are only ever set
  together, on an error — so checking one was a safe stand-in for "there's
  an error to show." Ollama's collector sets `usageStatusText` unconditionally
  as a normal label ("Running"/"Stopped"), which satisfied the visibility
  check without ever populating `authHelpText`, drawing the alarm box empty
  on every single refresh. Fixed by keying the banner's visibility on
  `authHelpText` itself — the field it actually displays — which is strictly
  more correct for every provider, not a special case for Ollama.

Verified with a screenshot: tab switcher at top, models + three buttons at
bottom, no more empty red box.
