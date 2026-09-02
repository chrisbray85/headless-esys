# Contributing

Thanks. Two kinds of contribution are most useful.

## Cheat sheets

- Keep the E-Sys Launcher / EsysUltra XML format and keep the `author` attribute
  on every `<cafd>`. Credit stays with whoever worked it out.
- One file per author or source. Do not merge other people's files into yours.
- Say which car and software level you verified it on, in the PR description.
- Run `python scripts/cheat_index.py` and commit the updated `cheatsheets/INDEX.md`
  (CI fails if the index is stale).

## Coordinate maps and gotchas

`docs/ui-controls.md` holds window layouts for a maximised app on a 1920×1080 screen.
If your laptop differs, add a section rather than editing the existing numbers, and
say the resolution and scaling. New gotchas go in `docs/GUIDE.md` with the symptom
first, then the cause, then the fix.

## Code

- Python: keep `ista_mcp/server.py` a single file; tools are small functions with a
  docstring that tells an agent when to use them and what is a write to the car.
- PowerShell helpers live in `scripts/` and are pushed to the laptop by `setup()`.
  They must stay DPI-aware and must not open a console window.
- Nothing in this repo may include BMW software, data, licence keys, VINs or
  personal identifiers. CI greps for the obvious ones; please check anyway.
- Run `scripts/smoke.py` against a real laptop before opening a PR that touches
  capture or input, and say so in the PR.

## Safety changes

Anything that loosens the "human go before a write" rule will not be merged.
