# A diagnostic session with the agent, start to finish

Written from a real one: a G20 with a charge-pressure fault, the agent driving ISTA+
on the garage laptop while the owner was at the car.

## 1. Kit

| Item | Notes |
|---|---|
| Windows laptop at the car | Win 10/11, on mains if possible. Battery mode silently stops the helper tasks until `setup()` fixes the task settings. |
| ENET cable (or ICOM) | OBD to RJ45. ISTA finds the car over it. |
| ISTA+ | Installed and working by hand first. If you can't diagnose manually, the agent can't either. |
| Remote route | Tailscale or similar into the laptop, SSH server on, desktop logged in. |
| This repo | The MCP server on your Mac/PC, registered with your MCP client. |

## 2. Before the first real session

Run, in order: `diagnose()`, `setup()`, `calibrate()`, `read_state()`. Calibration must
say 5/5 hits and a matching capture size. If it doesn't, the causes in the README cover
every one we hit: display scaling, battery, Defender, no desktop.

One ISTA-specific thing: ISTA may be set to run as administrator. Clicks from a
non-elevated helper are then discarded by Windows and it looks like ISTA ignores them.
The input task here runs elevated, so it works either way; `ista_elevation("status")`
tells you the state and `read_state()` warns if it matters.

## 3. A real case: a charge-pressure fault

**Symptom:** a stored charge-pressure control fault.

**What the agent did:**

1. `read_state()` with ISTA on the fault list. It read the codes as text and explained
   each one in plain English.
2. Opened the relevant fault; `read_doc()` pulled BMW's description and the full test
   plan in one call, German translated.
3. Looked the code up on the web for that engine, and reported where the community's
   experience agreed with BMW's plan and where it didn't.
4. Walked the test plan one step at a time, asking the owner for each check, until it
   reached the component BMW's plan blamed.
5. Component replaced. Fault cleared with a typed go, re-read: clean, and still clean
   on a full read the next day.

**What it didn't do:** it didn't guess. Where the plan asked for a measurement it
couldn't take, it said so and waited. It didn't clear the fault until told to.

## 4. Gotchas we met

- **`tempWebView.html` is UTF-8 but arrives re-encoded** if you read it naively over
  SSH. The helper decodes it properly; if you ever see mojibake, that's why.
- **Defender quarantines screen-capture scripts** silently. `setup()` adds the
  exclusion for `C:\ista-mcp`. If capture returns nothing, `diagnose()` first.
- **Windows display scaling** at 125% makes a DPI-unaware helper capture a crop and
  click 25% off. Fixed in the helpers, verified by `calibrate()`.
- **On battery, scheduled tasks don't start.** `setup()` clears that condition.
- **A hidden PowerShell still flashes a console** and steals focus. Helpers run
  through a VBScript launcher with no window.
- **Every ISTA report and dialog is modal.** Close it before the next action.
- **Hotspot links drop.** If a tool call errors, check `input.log` before repeating.

## 5. What to try next

- Guided test plans for other stored faults, one step at a time.
- Service functions with a typed go: battery registration after a new battery, mic
  calibration, adaptation resets.
- A "plug-in check": read faults on every connection, diff against last time, message
  you only if something new appears.

## 6. What this project will not do

Coding and programming with E-Sys. It was tried, it worked on our own car, and it was
dropped from the public tool because E-Sys has no guardrails and a confident agent in
front of an inexperienced user is how modules get bricked. If you need coding, learn
E-Sys by hand first. The earlier work is on the `esys` branch, unsupported.
