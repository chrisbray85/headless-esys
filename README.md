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
                                                                                   ├─ grab.ps1   (screenshot, interactive session)
                                                                                   └─ input.ps1  (click / type / key, opt-in)
```

The Windows box runs ISTA in a logged-in desktop session. SSH lands in a non-interactive
session (Windows "Session 0"), so screen capture and input are executed via `schtasks`
with the `/it` (interactive token) flag - the one trick that reaches the real desktop.

## Tools

| Tool | Kind | What |
|------|------|------|
| `setup()` | install | Copies the PS1 helpers up and registers the scheduled tasks. Run once. |
| `screenshot()` | read | Returns the live screen as an image - read fault memory, test plans, graphs, dialogs. |
| `list_sessions()` | read | Recent ISTA log-session folders, newest first. |
| `read_log(path, contains, tail)` | read | Read/grep/tail any file (ISTA logs, .properties, dumps). |
| `run(command)` | read | Read-only shell on the laptop (dir, reg query, tasklist, findstr, PowerShell). |
| `click(x, y)` | **opt-in** | Left-click at coordinates. |
| `type_text(text)` | **opt-in** | Type into the focused field. |
| `press_key(key)` | **opt-in** | ENTER / TAB / ESC. |

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

## Roadmap

- [x] Read-only core: screenshot, logs, sessions, shell (proven over SSH)
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
