# headless-esys

**Let an AI agent see and drive a BMW coding laptop.** An MCP server that connects a
Claude (or any MCP client) to a Windows laptop at the car, so the agent can read the
screen, read files and logs, and, when you allow it, click and type into
**EsysUltra / E-Sys** for coding and **ISTA+** for diagnosis. You stay in charge of
every write to the car.

Built and proven by a hobbyist on a 2018 G20 320d: three ECUs coded and verified in
one evening, with the agent doing the driving and the owner giving the go for each
write. The guide, the coordinate maps and the gotchas from that session are all here.

> This is a hobby tool for coding your own car. It does not contain or redistribute any
> BMW software or data. You bring your own licensed EsysUltra/E-Sys and psdzdata, and
> your own laptop.

## What it is, in plain words

You have a laptop in the garage with E-Sys or EsysUltra on it, plugged into the car.
Normally you sit at that laptop and click through the screens yourself. With this, the
laptop can sit there with nobody at it (headless), and an AI agent on your phone or
computer does the clicking for you, talking to you in chat:

- It **sees** the laptop screen and reads what is on it, including E-Sys's German
  property names and comments (`Kommentar=Status MSAFahrerwunsch …`), which it
  translates and explains as it goes.
- It **finds** the coding you asked for in the community cheat sheets, opens the right
  module, shows you the current value and what it will become.
- It **waits for you to say go**, then writes it, reads it back, and proves the car
  holds the new value.
- It **keeps the receipts**: before/after files, a timestamped log, the fault list.

You still plug the cable in, turn the ignition on, and say go. Everything else is
typed, not clicked.

## Credits

- **E-Sys** is BMW's engineering tool; **EsysUltra** is the independent front end that
  makes it usable (cheat-sheet pane, real-time backups, UltraAdmin). This project only
  drives it through its normal window; all the heavy lifting is theirs.
- **Cheat sheets** in [cheatsheets/](cheatsheets/) are community work, each file carrying
  its author's name; see [cheatsheets/README.md](cheatsheets/README.md).
- **ISTA+** is BMW's dealer diagnostic system. The text-first read tools here were first
  built for it and still work; it is not required for coding.

## What it does

| You want to | The agent does |
|---|---|
| Know what is wrong with the car | Opens the DTC reader, reads all modules, saves the list, explains the codes |
| Change a coding | Reads the module (backup), applies the cheat or edits the property, shows you before → after, waits for your **go**, codes it, reads it back to prove it |
| Check the car's software level | Reads the vehicle order and SVT, compares to your psdzdata |
| Drive a slow UI without the mouse | Screenshots, coordinate clicks, keyboard menu picks, in one helper pass |
| Not brick anything | Refuses to write without an explicit go per ECU; never clicks during a write; verifies by file comparison |

## How it works

```
MCP client (Claude Code)  ─stdio─▶  ista_mcp/server.py  ─ssh/scp over Tailscale─▶  Laptop at the car (Windows)
                                                                                    ├─ grab.ps1      screen capture (DPI-aware, JPEG)
                                                                                    ├─ input.ps1     click / right-click / double-click / keys / scroll / UIA
                                                                                    ├─ state.ps1     ISTA's rendered document as text, in one call
                                                                                    ├─ diagnose.ps1  why capture or input is not working
                                                                                    ├─ caltarget.ps1 calibration target window
                                                                                    └─ run-hidden.vbs launches the above with no console window
```

SSH lands in Windows "Session 0", which cannot see the desktop. Capture and input run
as scheduled tasks with the interactive token (`/it`), the input task elevated, and are
launched through a VBScript so no console window flashes on the desktop (a flash steals
focus and closes Java popup menus). Everything the agent needs from the laptop comes
back as text or a small JPEG, so it works over a phone hotspot.

## Quick start

**Laptop (Windows 10/11):** OpenSSH server enabled, your SSH user is a local admin, a
desktop session logged in (auto-login recommended), Tailscale or another route in,
EsysUltra/E-Sys installed with psdzdata. Set UltraAdmin's Memory to 4096 if you have
16 GB.

**Your machine:**

```bash
git clone https://github.com/chrisbray85/headless-esys.git && cd headless-esys
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
claude mcp add-json ista-garage --scope user '{
  "command": "'$PWD'/.venv/bin/python",
  "args": ["'$PWD'/ista_mcp/server.py"],
  "env": { "ISTA_MCP_SSH": "user@100.x.y.z", "ISTA_MCP_ALLOW_INPUT": "1" }
}'
```

**First session, in this order:** `diagnose()` → `setup()` → `calibrate()` →
`screenshot()`. Then hand the agent [AGENTS.md](AGENTS.md); it is written for the agent
to read.

From a terminal, `scripts/smoke.py --deploy` runs setup plus a read-only check of every
tool and prints PASS/FAIL per step.

## Calibration self-test

`calibrate()` opens a full-screen target on the laptop with five numbered markers, reads
the physical screen size, clicks each marker through the normal input path, and reports:

```
screen 1920x1080 · capture 1920x1080 (match) · hits 5/5 · max error 1 px
```

Anything less means the agent's clicks would land in the wrong place. The usual causes,
all handled by `setup()` on a fresh laptop: Windows display scaling (the helpers are
DPI-aware), the laptop on battery (scheduled tasks default to "don't start on
batteries"), Defender quarantining the scripts (an exclusion is added), or no desktop
logged in (`diagnose()` says so).

## Tools

| Tool | Kind | What |
|---|---|---|
| `diagnose()` | check | Names why capture/input is or isn't working: desktop, Defender, scheduler, battery, app state. |
| `setup()` | install | Pushes the helper scripts, registers the tasks, clears battery limits, adds the Defender exclusion. Idempotent. |
| `calibrate()` | check | Screen-size and five-point click accuracy test (needs input enabled). |
| `screenshot(fmt)` | read | One-shot frame, JPEG by default. The coordinate space for every click. |
| `start_stream()` / `latest_frame()` / `stop_stream()` | read | Near-live frames from a capture loop; cheap over a hotspot. |
| `read_state()` / `read_doc()` | read | ISTA's currently displayed document as text (no OCR). |
| `list_controls(app, name_filter)` | read | Real control names and positions for WPF apps (UltraAdmin, ISTA). Java apps return nothing; use the screen. |
| `list_sessions()` / `read_log()` / `run()` | read | ISTA session folders, any file, any read-only command on the laptop. |
| `click(x,y)` / `right_click` / `double_click` | input | Coordinate mouse actions (elevated, so they land in admin apps). |
| `input_sequence([...])` | input | Several actions in one helper pass, e.g. open a popup menu and pick an item by keyboard. |
| `type_text` / `press_key` / `scroll` | input | Keyboard and wheel. |
| `click_control(name, app)` | input | Act on a WPF control by name via UI Automation. |
| `ista_elevation(mode)` | admin | Read or change ISTA's run-as-admin layer. |

Input tools exist only when `ISTA_MCP_ALLOW_INPUT=1` is set. Every input tool's help
text carries the rule: read and navigate freely, never a write to the car without the
human's go.

## Documentation

- [docs/GUIDE.md](docs/GUIDE.md): the hobbyist coding guide. UltraAdmin settings,
  connect, read, backup, code, verify, every gotcha met, what was coded on a G20 320d
  with property names, fault notes, and the secure-coding caveat before you update
  software.
- [docs/ui-controls.md](docs/ui-controls.md): coordinate maps for UltraAdmin, the
  EsysUltra Coding view, the FDL editor, the DTC reader and the cheat pane, plus the
  proven click sequences.
- [cheatsheets/INDEX.md](cheatsheets/INDEX.md): every cheat entry by series, ECU, CAFD
  and property, generated from the XMLs.
- [AGENTS.md](AGENTS.md): the operating brief an agent reads before its first tool call.

## Proven so far

- Capture and input on a 1920×1080 laptop at 125% scaling, on battery, over a phone
  hotspot that dropped twice.
- UltraAdmin driven by UI Automation; EsysUltra driven by screenshot + coordinates,
  including Java popup menus and the cheat-sheet pane.
- On a 2018 G20 320d: Start/Stop memory, eight head-unit changes, colder air-con, all
  read back byte-identical; full DTC read of 21 modules.
- ISTA+: text-first document reads and UI Automation clicks were built and checked
  earlier; a full ISTA diagnostic session driven end to end is the next thing to prove.

## Roadmap

- `read_faults()` as structured data from EsysUltra's saved DTC file
- A "plug-in check": on every connection, read faults, diff against last time, report
- A coding profile file: everything coded on this car, re-applied in one pass after a
  software update
- ISTA+ end-to-end: test plan navigation and service functions through the same tools

## Disclaimer, read it

- **This is hobby software and it can be wrong.** The agent reads the screen and
  decides where to click. It asks you before any write to the car, but a wrong value
  you approve still gets written. Understand each change before you say go, and keep
  the backups it makes.
- **You are responsible for your car.** Coding can disable safety-relevant functions,
  void warranty, or breach local law (speedometer correction and video in motion are
  the usual examples). Check before you apply.
- **A failed flash can disable a module.** Software updates are outside what this
  project tests; read the secure-coding section of the guide before attempting one.
- **No affiliation** with BMW AG, EsysUltra, or the cheat-sheet authors. All names are
  their owners' trademarks. Nothing from BMW is included here.
- **No warranty.** MIT licence: provided as is.

## Safety, plainly

Coding writes to control units. This tool makes it easier, not safer. Keep the rules:
engine off and ignition on, one ECU at a time, backup before, verify after, charger on
for anything longer than a coding, and never update a module's software without
reading the secure-coding section of the guide first.

## License

MIT. See [LICENSE](LICENSE).
