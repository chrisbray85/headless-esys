# A diagnostic session with the agent, start to finish

Written from a real one: a 2018 G20 320d with a boost complaint, one evening, the agent
driving ISTA+ on the garage laptop while the owner was at the car.

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

## 3. The 244C00 case

**Symptom:** occasional boost hesitation, a charge-pressure fault stored.

**What the agent did:**

1. `read_state()` with ISTA on the fault list. It read the codes as text and explained
   each one. The relevant one: `244C00`, charge-pressure control, pressure converter.
2. Opened the fault; `read_doc()` pulled BMW's description and the test plan text in one
   call, in full, with the German translated.
3. Looked the code up on the web for a B47 G20. Community threads pointed at two things
   BMW's plan also covers: the electro-pneumatic pressure converter itself, and the
   vacuum lines to it, one of which routes near the oil dipstick and kinks.
4. Walked the test plan: check vacuum supply, check the converter's control line, inspect
   the hose routing. The owner found the kinked hose at the dipstick.
5. Fixed, fault cleared with a typed go, re-read: clean. The next full read a day later
   still showed no 244C00.

**What it didn't do:** it didn't guess. Where the plan asked for a vacuum reading, it
said so and waited. It didn't clear the fault until told to.

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
