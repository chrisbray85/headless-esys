# Operating brief for an AI agent using headless-esys

You are driving a Windows laptop at a BMW, through the `ista-garage` MCP server in
this repo. The laptop runs **EsysUltra** (E-Sys front end) for coding and may also run
**ISTA+** for diagnosis. You see the screen through `screenshot()` and act through
coordinate clicks and keys. This file tells you how to get going and what you must
never do. Read it fully before the first tool call.

## 0. Hard rules

Tell the human, once, at the start of a session: "I will ask before every write to the
car, but you must understand and agree each change; I can be wrong."

1. **Reads and navigation are yours. Writes to the car are the human's.** Read FA,
   read SVT, read DTCs, read coding data, open editors, apply cheats to the local file,
   save the file: do these on your own. **Code NCD / Code FDL / VO write / TAL
   execute / Clear DTCs: only after the human types an explicit go for that exact
   write**, and only one ECU at a time. Show them the before → after values first.
2. **Never click anything during a write.** Wait for "TAL execution finished".
3. **Engine off, ignition on** for all coding. Ask the human to confirm.
4. **A backup must exist before a write.** EsysUltra's real-time backup writes
   `NCD\<ECU>\1_READ_<CAFD>.ncd` when you Read Coding Data; check it is there.
5. **Verify every write** by reading the coding data again, then `verify_coding(ecu)`
   (it compares the read-back with the write and says VERIFIED or MISMATCH). A post-coding read may
   time out for a minute; wait and retry, or ask for an ignition off/on. Do not re-code.
6. **If a tool call errors, check before repeating.** `run('type C:\ista-mcp\input.log')`
   shows whether the action already ran. A dropped link can leave `action.txt` written
   but the task untriggered; `run('schtasks /run /tn IstaInput')` fires it.
7. Keep any single `run()` helper sequence under about 45 seconds of sleeps; the tool
   times out at 60 seconds and you lose the result, not the actions.

## 1. Install (once per machine)

```bash
git clone https://github.com/chrisbray85/headless-esys.git && cd headless-esys
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Register with Claude Code (adjust the paths and the SSH target):

```bash
claude mcp add-json ista-garage --scope user '{
  "command": "/path/to/headless-esys/.venv/bin/python",
  "args": ["/path/to/headless-esys/ista_mcp/server.py"],
  "env": { "ISTA_MCP_SSH": "user@100.x.y.z", "ISTA_MCP_ALLOW_INPUT": "1" }
}'
```

- `ISTA_MCP_SSH` is required: the laptop's SSH login, usually over Tailscale. Key
  authentication must already work from a terminal (`ssh user@100.x.y.z hostname`).
- `ISTA_MCP_ALLOW_INPUT=1` enables the click/type tools. Leave it out for a read-only
  agent. It is read once at server start; changing it needs a reconnect.

Laptop prerequisites: Windows 10/11, OpenSSH server enabled, the SSH user is a local
administrator, a desktop session logged in (auto-login is the reliable way), and
EsysUltra/ISTA installed by the owner.

## 2. First contact checklist (run in this order)

1. `diagnose()` — must show `desktop=True`, `defender_excluded=True`, `scheduler_ok=True`.
   If the scheduler is not executing and `on_battery=True`, run `setup()` (it clears
   the battery restriction) or ask for mains power.
2. `setup()` — pushes the helper scripts and registers the scheduled tasks. Safe to
   repeat. Run it after any update to `scripts/`.
3. `calibrate()` — puts a target window on the laptop screen, clicks its five markers
   and reports whether capture size matches the physical screen and whether each click
   landed on its target. **Do not drive any app until this passes 5/5.** A cropped
   capture with no taskbar means display scaling is wrong; `setup()` deploys DPI-aware
   helpers, so re-run it.
4. `screenshot()` — look at the desktop. Note the resolution; every coordinate you use
   is a pixel in this image.

## 3. How to drive the apps

- **UltraAdmin / ISTA / other WPF apps:** `list_controls(app=...)` gives real control
  names and positions; `click_control(name)` acts by name. Names can be empty (then
  use the AutomationId row's centre with `click`).
- **EsysUltra / E-Sys (Java):** no UI automation. `screenshot()` → read → `click(x,y)`.
  Popup menus: open with `right_click`, pick with keys in the same helper pass:
  `input_sequence(["RCLICK x y", "KEY {DOWN}{DOWN}{ENTER}"])`. Clicking a popup item
  directly is unreliable.
- Every E-Sys report window is modal; close it before the next click. Tree rows shift
  down when a node is expanded; screenshot again before clicking a row.
- Coordinate maps of the windows seen so far: [docs/ui-controls.md](docs/ui-controls.md).
  Positions are for a maximised window on a 1920×1080 screen; confirm with a screenshot
  on a different laptop.

## 4. The coding sequence

Full detail with gotchas: [docs/GUIDE.md](docs/GUIDE.md) section 5. Short form:

Expert Mode → Coding → Read FA → Read SVT (ECU) → select CAFD → Read Coding Data →
expand → right-click child → Edit NCD → (cheat pane: Reload, search, select, Review,
Apply) or (manual: search property, edit value) → Save → Expert Mode → Coding →
**human go** → Code NCD → close both reports → Read Coding Data → compare files.

Cheat sheets with property names and values: [cheatsheets/INDEX.md](cheatsheets/INDEX.md).
German terms: [docs/GLOSSARY.md](docs/GLOSSARY.md). Faults: `read_faults()` after a DTC
read with Copy As File. Backups: `list_backups()`.

## 5. Reporting to the human

- Before a write: ECU, CAFD, each property before → after, what it does, and that the
  backup exists. Then wait for the go.
- After a write: the TAL status, the verification result, and any fault codes that
  appeared.
- Keep a running log file of what was read and written, with timestamps, so the
  session can be reconstructed if the link drops.
