# CLAUDE.md

Working conventions for Claude Code in this repo. This repo is a versioned
archive of Omarchy customizations whose *live* files sit elsewhere on disk
(`~/.config`, `~/.local/bin`, `~/.config/systemd/user`, etc.) — see the root
[`README.md`](README.md) for the organizing idea.

## Making an actual Omarchy customization

Editing anything under `~/.config/hypr/`, `~/.config/omarchy/`, or other live
Omarchy config is a separate concern from this repo. Use the `omarchy` skill
for that work (it covers safe customization patterns, what never to touch
under `/usr/share/omarchy/`, and privilege-escalation rules). This repo is
where the *result* of that work gets documented and versioned once it's
working — not a substitute for the skill while doing it.

## Adding or updating a project here

1. One top-level folder per project, `kebab-case-named` for what it does.
2. Every project folder needs a `README.md`: what it does, why, an exact
   table mapping the files in the folder to their live path on disk, and
   how to reapply it from scratch on a fresh machine or account.
3. If the work took more than one back-and-forth revision, add a
   `DEVLOG.md` alongside it: a chronological account of what was tried,
   what was learned, and what changed between rounds. Keep this out of the
   README — the README is a clean reference, the devlog is the history.
4. Structure files under the project folder by *role*
   (`plugin/<id>/`, `bin/`, `systemd/user/`, …), matching the tables in
   `agents-panel-ollama/README.md` as the pattern to follow — not by the
   literal absolute path on any one machine (usernames and home directories
   differ across machines/accounts).
5. **Update the root `README.md`'s project table in the same change.** This
   is a hard requirement from the repo owner: the index must never drift
   from what the repo actually contains. Do this whenever a project is
   added, renamed, or its one-line description stops matching what it does.
6. Keep the snapshot in sync with the live files. If you're asked to save,
   commit, or archive further changes to something already documented here,
   re-copy the current live files over the snapshot before writing about
   the change — don't describe a change without updating the files that are
   supposed to demonstrate it.

## Git

- Follow the standing Claude Code git policy: create commits only when the
  user explicitly asks, never amend or force-push without being asked, and
  write commit messages that explain *why*, not just what changed.
- This repo may be public (check the owner's current answer in the root
  README's history / ask if unsure). Before staging or committing:
  - Never commit secrets, API keys, tokens, private key material, or
    session/auth data — even inside a config file that looks innocuous
    (shell.json, systemd units, scripts pulled from `~/.local/bin`).
  - Scripts and configs will legitimately contain the local Linux username
    (Omarchy's `omarchy plugin clone` names clones `<username>.<plugin>`,
    e.g. `olp.agents`) — that's expected and not sensitive on its own, but
    don't let anything more identifying (real name, email, hostname, IP,
    Wi-Fi credentials, etc.) slip in through a copied config file.
  - When in doubt, `grep` the new/changed files for things that look like
    keys, tokens, emails, or hostnames before staging, the same way you
    would before any other push.

## Licensing

This repo is MIT-licensed (see `LICENSE`). Omarchy itself is MIT-licensed;
where a project here clones or edits Omarchy's own shell/plugin source
(e.g. `agents-panel-ollama/plugin/`), that lineage is noted in the project's
own README rather than repeated here.
