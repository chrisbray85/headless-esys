# ISTA-MCP

Drive a remote BMW **ISTA+** garage laptop from any MCP client (Claude Code, etc).
Turns a manual "SSH in, screenshot ISTA, read the fault, reason about it, decide the
next click" workflow into repeatable tools.

Built for one person diagnosing their own cars. It does not redistribute BMW's data;
it reads the screen and logs of an ISTA install you already run.

## Why

ISTA holds BMW's entire diagnostic knowledge base (fault databases, guided test plans,
wiring, repair procedures) but its UI is slow to drive by hand and impossible to
automate through. This wraps a headless garage laptop so an LLM can *read* ISTA's
content as text, *see* its graphs, and - opt-in - *act* on it, while the human stays
in the loop for anything that touches the car.

## Architecture

```
MCP client (Claude)  ──stdio──▶  ista_mcp/server.py  ──ssh/scp over Tailscale──▶  Garage laptop (Windows + ISTA+)
                                                                                   ├─ state.ps1  (ONE call: doc HTML + frame + ISTA status)
                                                                                   ├─ grab.ps1   (one-shot + continuous-loop capture, interactive session)
                                                                                   ├─ input.ps1  (UIA click-by-name / coordinate click / type / key, opt-in)
                                                                                   └─ elev.ps1   (RUNASADMIN layer on/off - why clicks land or don't)
```

The Windows box runs ISTA in a logged-in desktop session. SSH lands in a non-interactive
session (Windows "Session 0"), so screen capture and input are executed via `schtasks`
with the `/it` (interactive token) flag - the one trick that reaches the real desktop.
`state.ps1` and `elev.ps1` only read files / HKCU, so they run directly over SSH.

### The two design rules (learned diagnosing a real fault)

1. **Read text as text, not as pixels.** ISTA renders whatever document/procedure/
   fault description it is displaying as HTML to `%LOCALAPPDATA%\Temp\tempWebView.html`.
   `read_doc()` / `read_state()` pull and parse that: full text in one round-trip - no
   OCR, no screen-edge clipping, no screenshot-scp-read-repeat loop. Screenshots are
   reserved for genuinely graphical things (live actuation-test traces, dialog state).
2. **Input only lands in a non-elevated ISTA.** ISTA set to always-run-as-admin means
   Windows UIPI silently discards injected clicks from a medium-integrity helper -
   screenshots keep working, so it looks like ISTA "ignored" the click. Diagnosis
   doesn't need admin (only programming/coding does): `ista_elevation("off")` +
   restart ISTA, and clicks land. `click_control(name)` then drives ISTA's WPF UI via
   UIAutomation (Invoke/Select by control name - robust against layout shifts),
   falling back to coordinate clicks only when a control exposes no pattern.

## Tools

| Tool | Kind | What |
|------|------|------|
| `setup()` | install | Copies the PS1 helpers up and registers the scheduled tasks. Run once (and after editing the PS1s). |
| `read_state(with_frame, fresh_ms)` | read | **Primary read.** One round-trip: parsed text of ISTA's displayed document + one JPEG frame + ISTA running/elevated status. |
| `read_doc(raw)` | read | Just the displayed document's full text (from `tempWebView.html`), fastest path. `raw=True` for the untouched HTML. |
| `list_controls(name_filter)` | read | ISTA's actionable controls by real UIA name (buttons, tabs, items). The menu for `click_control()`. |
| `ista_elevation(mode)` | admin | `status` / `off` / `on` for the RUNASADMIN layer - the reason clicks do or don't land. |
| `screenshot(fmt="jpg")` | read | One-shot live screen as an image - for graphs/dialog state. `jpg` = compressed (~tens of KB, default); `png` = lossless (~600 KB) fallback. |
| `start_stream(quality, interval_ms, scale, max_seconds)` | read | Start a continuous capture loop on the laptop writing the newest frame to `live.jpg`. |
| `latest_frame()` | read | **Fast/near-live:** pull the newest streamed frame - no scheduler trigger, no wait. Falls back to `screenshot()` if no stream is running. |
| `stop_stream()` | read | Stop the capture loop (saves hotspot bandwidth + CPU). |
| `list_sessions()` | read | Recent ISTA log-session folders, newest first. |
| `read_log(path, contains, tail)` | read | Read/grep/tail any file (ISTA logs, .properties, dumps). |
| `run(command)` | read | Read-only shell on the laptop (dir, reg query, tasklist, findstr, PowerShell). |
| `click_control(name)` | **opt-in** | Act on an ISTA control **by name** via UIAutomation (Invoke/Select/Toggle/Expand, centre-click fallback). Preferred over `click()`. |
| `click(x, y)` | **opt-in** | Left-click at coordinates (fallback when a control exposes no name). |
| `type_text(text)` | **opt-in** | Type into the focused field. |
| `press_key(key)` | **opt-in** | ENTER / TAB / ESC. |
| `scroll(notches)` | **opt-in** | Mouse-wheel the window under the cursor (negative = down). |

## Fast capture / near-live streaming

Watching ISTA used to mean ~10-15 s per still: trigger a scheduled task, wait a fixed
4 s, then `scp` a ~600 KB PNG back - and each `ssh`/`scp` paid a fresh handshake, which
hurts most over a phone hotspot. Three changes attack every part of that:

1. **Compressed JPEG instead of PNG** (`grab.ps1`). A 1536x864 ISTA frame drops from
   ~600 KB (PNG) to roughly:

   | Setting | ~Size | vs PNG | Notes |
   |---------|-------|--------|-------|
   | JPEG q55, full res (default) | ~60-90 KB | ~-85% | UI text stays crisp |
   | JPEG q45, scale 0.75 | ~30-45 KB | ~-93% | large ISTA text still readable; tiny digits soften |
   | PNG full (`fmt="png"`) | ~600 KB | - | lossless fallback for pixel-peeping a graph |

2. **Continuous capture loop** (`start_stream()` -> `IstaGrabLoop`). A single
   always-running PowerShell loop in the interactive session writes the newest frame to
   `C:\ista-mcp\live.jpg` every ~`interval_ms` (atomic temp-then-rename). `latest_frame()`
   just pulls that file - **no per-frame `schtasks /run`, no 4 s sleep**. Stops cleanly
   via a stop-sentinel file (`stop_stream()`), and auto-stops after `max_seconds` so a
   forgotten stream can't drain data/CPU. On exit it deletes `live.jpg`, so
   `latest_frame()` can tell the stream is gone and fall back to a one-shot.

3. **SSH connection multiplexing** (`ControlMaster` in `server.py`). One tunnel is
   opened and kept warm for 2 min, so every `ssh`/`scp` after the first skips the
   TCP+SSH handshake - the part that stings most on a high-latency hotspot. Helps every
   tool, not just capture.

Net effect: the near-live path (`start_stream()` once, then `latest_frame()`) is a
single small `scp` over a warm tunnel - typically well under a second per frame instead
of 10-15 s.

### Why not a real MJPEG / ffmpeg stream?

Considered and **not** recommended here (over a hotspot, for an LLM viewer):

- **An LLM consumes discrete frames, not video.** It looks at a still, reasons, acts,
  looks again. A continuous 15-30 fps stream buys nothing a ~1 fps pull-on-demand
  doesn't - the model can't "watch" between tool calls.
- **A push stream burns data continuously.** Even 2 fps x 70 KB is ~1 Mbit/s sustained
  whether or not anyone is looking, competing with ISTA's own online needs on a metered
  hotspot. Pull-on-demand only moves bytes when the model actually wants a frame.
- **`ffmpeg gdigrab` adds a dependency and CPU load** and *still* has to run in the
  interactive session (the same Session 0 limitation), on a laptop already busy with
  ISTA - for a stream you'd only ever sample stills from anyway.

A tiny HTTP `/frame.jpg` endpoint bound to the Tailscale IP would shave a little more
per-frame latency than multiplexed `scp` (no scp process spawn), but it means a
long-running service + open port on the garage box for a marginal win. **Recommendation:
pull-on-demand compressed JPEGs via the capture loop is the right trade over a hotspot.**
Keep the HTTP endpoint on the shelf only if per-frame latency ever needs to be shaved
to the floor.

## Safety

- **Input is off by default.** The click/type/key tools do nothing unless
  `ISTA_MCP_ALLOW_INPUT=1` is set.
- **Never enable input during a flash / coding / actuator write on a live car.**
  A mis-timed click there can brick a module. Read-only observation is always safe.
- **Personal use.** Reading your own ISTA install for your own cars is the intended use.
  Building a public/commercial product on ISTA's licensed content is not - that is what
  BMW's paid Aftersales APIs license.

## Setup

```bash
pip install -r requirements.txt        # needs the `mcp` SDK
export ISTA_MCP_SSH="user@100.x.y.z"   # your garage laptop over Tailscale
# optional, only when you want it to click:
# export ISTA_MCP_ALLOW_INPUT=1
```

Register with Claude Code:

```bash
claude mcp add ista-garage --scope user -- python /path/to/ista-mcp/ista_mcp/server.py
```

Then, once connected, call `setup()` a single time to install the helper scripts and
scheduled tasks on the laptop. After that, `screenshot()` and the read tools work.

Prerequisites on the laptop: SSH server enabled, a logged-in desktop session, ISTA+
installed. All of these are already true for the garage build.

## First session after the v2 (text-first) upgrade

> Do this when no car job is running. Nothing here writes to a vehicle.

One command from the Mac deploys and verifies everything:

```bash
.venv/bin/python scripts/smoke.py --deploy
```

It checks, in order: SSH; `setup()` (adds the Defender exclusion, pushes all four
PS1s, registers tasks); `ista_elevation("status")`; `read_doc()`; `read_state()`
(text + frame in one call); `screenshot()`; a `PING` through the input task;
`list_controls()`; `list_sessions()`. Each step prints PASS/FAIL and keeps going.

**Then, to make clicks land (one-time):** `ista_elevation("off")` and restart ISTA
normally (not "run as administrator"). Flip back with `ista_elevation("on")` before a
programming/coding session. While ISTA runs elevated, `list_controls()` still works
(UIA reads cross the integrity boundary) but `click_control()`/`click()` are discarded
by UIPI - `read_state()`'s status line warns about exactly this.

### Two gotchas found on first live deploy (2 Sep 2026)

- **Windows Defender silently quarantines the scripts.** Screen-capture + SendInput
  PowerShell trips Defender's `ScriptContainedMaliciousContent` heuristic, so
  `screenshot()` just produces no frame with no obvious error. ISTA's own dirs
  (`C:\BMW`, `C:\ISTA-setup`, ...) were already Defender-excluded, which is the only
  reason the earlier hand-built setup worked. `setup()` now adds `C:\ista-mcp` to the
  exclusion list automatically (best-effort; needs the admin SSH token OpenSSH grants
  an admin user). Undo by hand with `Remove-MpPreference -ExclusionPath C:\ista-mcp`.
- **Capture/input need the console session free.** The `/it` tasks run in the
  logged-on console session; if an installer or a UAC modal is holding that session
  (or it's disconnected), the task launches (`schtasks` returns 0) but the payload
  lands in Session 0 and never reaches the desktop - empty screenshots, unlogged
  input. Make sure a desktop is logged in and idle. `read_doc()`/`read_state()` text
  still works regardless (it's a plain file read over SSH).

**Confirmed live (2 Sep 2026):** SSH, `setup()`, `read_doc()`/`read_state()` text
(after a UTF-8 output fix - `tempWebView.html` is real and parses), `list_sessions()`,
Defender exclusion, ISTA integrity probe (ISTA was running HIGH/elevated).
**Still to verify with the console session free:** task-driven `screenshot()`/frame
capture, `list_controls()` UIA tree contents (are test-plan buttons named?),
`click_control()` after dropping elevation, `tempWebView.html` freshness per ISTA view.

## Roadmap

- [x] Read-only core: screenshot, logs, sessions, shell (proven over SSH)
- [x] Fast capture: compressed JPEG + continuous-loop `latest_frame()` + SSH multiplexing (near-live over a hotspot)
- [x] Opt-in coordinate input: click / type / key
- [x] **Text-first reads** - `read_doc()`/`read_state()` parse ISTA's own rendered HTML
      (`tempWebView.html`): full text, one round-trip, no OCR *(needs live verify)*
- [x] **UI Automation input** - `list_controls()` + `click_control(name)` drive ISTA's
      WPF controls by name instead of x/y *(needs live verify)*
- [x] Elevated input past UIPI - the IstaInput task runs `/rl HIGHEST`, so clicks
      land into an *elevated* ISTA with no restart (works because the SSH login is
      admin; verified RunLevel=Highest, click execution pending the post-reboot test).
      `ista_elevation()` (toggle the RUNASADMIN layer + restart ISTA) is the fallback
- [ ] `read_faults()` - fault memory as structured data (find ISTA's export/session
      files rather than scraping the UI; candidates under `C:\ProgramData\BMW\ISPI`)
- [ ] A guided "diagnose this fault" prompt that chains read_state -> reason -> next step
- [ ] Session recorder: log every read + action as a repeatable diagnostic script

## Status

The SSH/capture/log primitives are proven in practice. The v2 text-first layer
(`state.ps1`, UIA input, elevation control) is built and syntax-checked but **not yet
run against the live laptop** - `scripts/smoke.py --deploy` is the one-command
deploy-and-verify for the next time the garage laptop is online.
