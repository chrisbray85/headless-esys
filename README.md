# ISTA-MCP

Drive a remote BMW **ISTA+** garage laptop from any MCP client (Claude Code, etc).
Turns a manual "SSH in, screenshot ISTA, read the fault, reason about it, decide the
next click" workflow into repeatable tools.

Built for one person diagnosing their own cars. It does not redistribute BMW's data;
it reads the screen and logs of an ISTA install you already run.

## Why

ISTA holds BMW's entire diagnostic knowledge base (fault databases, guided test plans,
wiring, repair procedures) but its UI is slow to drive by hand and impossible to
automate through. This wraps a headless garage laptop so an LLM can *see* ISTA
(screenshots), *read* its logs, and - opt-in - *act* on it, while the human stays in
the loop for anything that touches the car.

## Architecture

```
MCP client (Claude)  ──stdio──▶  ista_mcp/server.py  ──ssh/scp over Tailscale──▶  Garage laptop (Windows + ISTA+)
                                                                                   ├─ grab.ps1   (one-shot + continuous-loop capture, interactive session)
                                                                                   └─ input.ps1  (click / type / key, opt-in)
```

The Windows box runs ISTA in a logged-in desktop session. SSH lands in a non-interactive
session (Windows "Session 0"), so screen capture and input are executed via `schtasks`
with the `/it` (interactive token) flag - the one trick that reaches the real desktop.

## Tools

| Tool | Kind | What |
|------|------|------|
| `setup()` | install | Copies the PS1 helpers up and registers the scheduled tasks. Run once (and after editing the PS1s). |
| `screenshot(fmt="jpg")` | read | One-shot live screen as an image. `jpg` = compressed (~tens of KB, default); `png` = lossless (~600 KB) fallback. |
| `start_stream(quality, interval_ms, scale, max_seconds)` | read | Start a continuous capture loop on the laptop writing the newest frame to `live.jpg`. |
| `latest_frame()` | read | **Fast/near-live:** pull the newest streamed frame - no scheduler trigger, no wait. Falls back to `screenshot()` if no stream is running. |
| `stop_stream()` | read | Stop the capture loop (saves hotspot bandwidth + CPU). |
| `list_sessions()` | read | Recent ISTA log-session folders, newest first. |
| `read_log(path, contains, tail)` | read | Read/grep/tail any file (ISTA logs, .properties, dumps). |
| `run(command)` | read | Read-only shell on the laptop (dir, reg query, tasklist, findstr, PowerShell). |
| `click(x, y)` | **opt-in** | Left-click at coordinates. |
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

## Deploying the fast-capture upgrade

> The garage laptop is often mid-diagnosis. **Do this only when no car job is running**
> (registering tasks and the first capture briefly touch the desktop session). Nothing
> here writes to a vehicle.

**What to push:** just the updated `scripts/grab.ps1` (the new `server.py` runs on the
Mac and needs no laptop-side deploy). The safe path is simply to re-run `setup()` from
the MCP client - it copies `grab.ps1` up and (re)registers the tasks.

**To deploy:**

1. From the MCP client, call `setup()` once. This copies `grab.ps1` and registers
   `IstaGrab` (JPEG one-shot), `IstaGrabPng` (PNG fallback) and `IstaGrabLoop` (stream).
   (Equivalent by hand: `scp scripts/grab.ps1 user@100.x.y.z:C:/ista-mcp/grab.ps1`,
   then the three `schtasks /create ... /it /f` lines `setup()` runs.)
2. Verify the one-shot: `screenshot()` should return a small JPEG.
3. Verify the stream: `start_stream()`, then a couple of `latest_frame()` calls, then
   `stop_stream()`.

**Must be tested live (can't be verified off-Windows):**

- The GDI+ JPEG encode + optional scale in `grab.ps1` (System.Drawing is Windows-only;
  the control-flow/config/loop logic *was* verified on PowerShell Core). Confirm actual
  `live.jpg`/`screen.jpg` sizes and that ISTA text is legible at the chosen `quality`.
- That `IstaGrabLoop` runs in the **interactive** session (same `/it` trick as `IstaGrab`)
  and that `live.jpg` updates continuously without pinning CPU while ISTA runs.
- The atomic temp-then-rename vs. a concurrent `scp` read (the `scp` side retries once;
  confirm no torn frames in practice).

**Heads-up - path/task naming.** This repo standardises on `C:\ista-mcp\` and tasks
`IstaGrab` / `IstaGrabLoop` (what `server.py` expects). If the live laptop was set up
by hand with different names/paths (e.g. `C:\ISTA-setup\live-screen.png` / a `GrabScreen`
task), re-running `setup()` brings it onto the canonical layout. If you'd rather keep the
existing live layout, change `REMOTE_DIR` in `server.py` to match instead. Either way,
`server.py` and the registered tasks must agree.

**Revert:** the previous `grab.ps1` produced `C:\ista-mcp\screen.png`; `screenshot()`
still falls back to `screen.png` if `screen.jpg` isn't present, so an un-upgraded laptop
keeps working. To fully roll back, `git checkout` the old `grab.ps1` + `server.py` and
re-run `setup()`.

## Roadmap

- [x] Read-only core: screenshot, logs, sessions, shell (proven over SSH)
- [x] Fast capture: compressed JPEG + continuous-loop `latest_frame()` + SSH multiplexing (near-live over a hotspot)
- [x] Opt-in coordinate input: click / type / key
- [ ] **UI Automation input** - click ISTA controls by name/AutomationId instead of x/y
      (robust against layout shifts; the right long-term way to drive a WPF app)
- [ ] `read_faults()` - parse ISTA's fault-memory export into structured JSON
- [ ] A guided "diagnose this fault" prompt that chains screenshot -> read -> reason
- [ ] Session recorder: log every screenshot + action as a repeatable diagnostic script

## Status

The SSH/screenshot/log primitives are proven in practice. First run needs one `setup()`
call to install the laptop-side helpers. UI-Automation input and structured fault parsing
are the next milestones.
