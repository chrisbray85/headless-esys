# Contributing

Most useful, in order:

1. **Session write-ups.** A fault code, what ISTA's plan said, what the agent did, what
   fixed it. Add a section to `docs/GUIDE.md` with symptom, code, steps, outcome. No
   VIN, no personal data.
2. **Control names.** `list_controls()` output for ISTA screens you drove, so
   `click_control()` can be used by name. Add them to a `docs/ista-controls.md`.
3. **Code.** Keep `ista_mcp/server.py` a single file; tools are small functions whose
   docstring tells an agent when to use them and whether they write to the car.
   PowerShell helpers in `scripts/` must stay DPI-aware and must not open a console
   window. Run `scripts/smoke.py` against a real laptop before a PR that touches
   capture or input, and say so.

Rules:

- Nothing in this repo may include BMW software, data, licence keys, VINs or personal
  identifiers. CI greps for the obvious ones; check anyway.
- Anything that loosens "typed go before a write" will not be merged.
- Coding/programming features belong on the `esys` branch, not main.
