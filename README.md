# Omarchy customizations

Personal collection of [Omarchy](https://omarchy.org/) customizations, small
tools, and shell/plugin modifications — the stuff that lives in `~/.config`,
`~/.local/bin`, and `~/.config/systemd/user` on this machine but isn't
tracked anywhere else. Each subfolder is one self-contained piece of work:
a widget tweak, a new plugin, a script, a keybinding set, whatever. This
repo is the durable, versioned record of it — the live files it describes
are elsewhere on disk (paths given in each project's own README).

Omarchy itself (Arch Linux + Hyprland + a Quickshell-based shell) is
[MIT-licensed](https://github.com/basecamp/omarchy). Where a project here
clones or edits Omarchy's own shell/plugin source, that lineage is called
out in the project's README.

## How this repo is organized

- One top-level folder per project, named for what it does
  (`kebab-case-like-this`).
- Every project folder has its own `README.md`: what it does, why, exactly
  which live files on disk it corresponds to, and how to reapply it from
  scratch. Anything nontrivial that took more than one pass also gets a
  `DEVLOG.md` — a chronological account of how it evolved, kept separate
  from the README so the README can stay a clean reference instead of a
  history.
- Files under a project folder mirror the *role* of their live counterpart
  (`plugin/<id>/`, `bin/`, `systemd/user/`, …), not the literal absolute
  path on this machine — that mapping is spelled out in a table in each
  project's README instead.
- **This file is an index and must be kept current.** Whenever a project is
  added, renamed, or meaningfully changed, update its entry below in the
  same commit. Don't let this list drift from what's actually in the repo.

See [`CLAUDE.md`](CLAUDE.md) for the working conventions Claude Code follows
in this repo.

## Projects

| Project | What it does |
|---|---|
| [`agents-panel-ollama/`](agents-panel-ollama/README.md) | Adds Ollama as a third tab (alongside Claude Code and Codex) in Omarchy's built-in Agents bar widget — status, installed models, and Start/Stop/Refresh controls for a local Ollama server. |
