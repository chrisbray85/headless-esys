#!/usr/bin/env python3
"""Field deploy + verify for ISTA-MCP. Run from the Mac when the garage laptop is
online:  .venv/bin/python scripts/smoke.py [--deploy]

--deploy runs setup() first (pushes the ps1 scripts + registers tasks). Every step
reports PASS/FAIL and keeps going, so one broken piece doesn't hide the rest.
Read-only except for the deploy and one PING through the input task."""
import argparse
import subprocess
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ista_mcp import server  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def step(name: str, fn):
    t0 = time.time()
    try:
        out = fn()
        ok = True
    except Exception as e:
        out, ok = f"{type(e).__name__}: {e}", False
    ms = (time.time() - t0) * 1000
    summary = str(out).strip().splitlines()[0][:110] if out else "(empty)"
    RESULTS.append((name, ok, summary))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<18} {ms:6.0f}ms  {summary}")
    return out if ok else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", action="store_true", help="run setup() first")
    args = ap.parse_args()

    def reachable():
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes",
                            server.GARAGE, "echo ok"], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr.strip() or "ssh failed")
        return "garage laptop reachable"

    if step("ssh", reachable) is None:
        print("\nGarage laptop unreachable - nothing else can run.")
        sys.exit(1)

    if args.deploy:
        step("setup", server.setup)

    step("elevation", lambda: server.ista_elevation("status"))
    step("read_doc", lambda: server.read_doc())

    def read_state():
        parts = server.read_state(with_frame=True)
        text = parts[0]
        frame = next((p for p in parts[1:] if not isinstance(p, str)), None)
        fb = len(frame.data) if frame is not None and hasattr(frame, "data") else 0
        return f"{text.splitlines()[0]} | frame_bytes={fb}"
    step("read_state", read_state)

    step("screenshot", lambda: f"{len(server.screenshot('jpg').data)} bytes")
    step("ping_input", lambda: server._action("PING"))
    step("list_controls", lambda: server.list_controls())
    step("sessions", lambda: server.list_sessions(3))

    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed"
          + (f" - FAILED: {', '.join(failed)}" if failed else " - all good"))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
