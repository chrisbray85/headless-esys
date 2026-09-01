#!/usr/bin/env python3
"""ISTA-MCP - drive a remote BMW ISTA+ garage laptop from an MCP client.

The read-only tools (screenshot, read_log, list_sessions, run) are the safe core
and are built on primitives proven by hand over SSH + Tailscale. The input tools
(click, type_text, press_key) are OPT-IN via ISTA_MCP_ALLOW_INPUT=1.

HARD RULE: never enable input during a flash / coding / actuator write on a live
car. Observe freely; any action that changes vehicle state stays human-confirmed.
"""
import os
import pathlib
import subprocess
import tempfile
import time

from mcp.server.fastmcp import FastMCP, Image

GARAGE = os.environ.get("ISTA_MCP_SSH", "user@100.x.y.z")
REMOTE_DIR = "C:/ista-mcp"
ISTA_LOGS = r"C:\ProgramData\BMW\ISPI\Logs\TRIC\ISTA"
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
ALLOW_INPUT = os.environ.get("ISTA_MCP_ALLOW_INPUT") == "1"
SSH_OPTS = ["-o", "ConnectTimeout=10", "-o", "BatchMode=yes"]

mcp = FastMCP("ista-garage")


def _ssh(cmd: str, timeout: int = 40) -> str:
    r = subprocess.run(["ssh", "-n", *SSH_OPTS, GARAGE, cmd],
                       capture_output=True, text=True, timeout=timeout)
    out = r.stdout or ""
    if r.returncode and r.stderr:
        out += f"\n[stderr] {r.stderr.strip()}"
    return out.strip()


def _scp(src: str, dst: str, timeout: int = 30) -> None:
    subprocess.run(["scp", *SSH_OPTS, src, dst], check=True,
                   capture_output=True, text=True, timeout=timeout)


@mcp.tool()
def setup() -> str:
    """One-time install: copy the helper scripts to the garage laptop and register
    the scheduled tasks that let screenshot() and the input tools run in the
    interactive desktop session. Run this once before first use."""
    _ssh(f'if not exist "{REMOTE_DIR.replace("/", chr(92))}" mkdir "{REMOTE_DIR.replace("/", chr(92))}"')
    for f in ("grab.ps1", "input.ps1"):
        _scp(str(SCRIPTS / f), f"{GARAGE}:{REMOTE_DIR}/{f}")
    base = f'powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File {REMOTE_DIR.replace("/", chr(92))}'
    _ssh(f'schtasks /create /tn IstaGrab /tr "{base}\\grab.ps1" /sc once /st 23:59 /it /f')
    _ssh(f'schtasks /create /tn IstaInput /tr "{base}\\input.ps1" /sc once /st 23:59 /it /f')
    return "Installed grab.ps1 + input.ps1 and the IstaGrab / IstaInput tasks. screenshot() is ready."


@mcp.tool()
def screenshot() -> Image:
    """Capture the garage laptop's screen right now - i.e. whatever ISTA is showing.
    Use this to read fault memory, test-plan results, graphs and dialog boxes."""
    _ssh("schtasks /run /tn IstaGrab", timeout=20)
    time.sleep(4)
    local = tempfile.mktemp(suffix=".png")
    _scp(f"{GARAGE}:{REMOTE_DIR}/screen.png", local)
    return Image(data=pathlib.Path(local).read_bytes(), format="png")


@mcp.tool()
def list_sessions(limit: int = 8) -> str:
    """List recent ISTA diagnostic log-session folders, newest first. Each folder
    holds the logs for one ISTA run (fault reads, test plans, programming)."""
    lines = _ssh(f'dir /b /o-d /ad "{ISTA_LOGS}"').splitlines()
    return "\n".join(lines[:limit]) or "(no sessions found)"


@mcp.tool()
def read_log(path: str, contains: str = "", tail: int = 200) -> str:
    """Read a file on the garage laptop (ISTA logs, .properties, registry dumps).
    Optionally keep only lines containing `contains`, and/or the last `tail` lines.
    Find session paths with list_sessions(); the ISTA log root is
    C:\\ProgramData\\BMW\\ISPI\\Logs\\TRIC\\ISTA ."""
    if contains:
        cmd = (f'powershell -NoProfile -Command "Get-Content \'{path}\' | '
               f'Select-String -SimpleMatch \'{contains}\' | Select-Object -Last {tail} | '
               f'ForEach-Object {{ $_.Line }}"')
    else:
        cmd = f'powershell -NoProfile -Command "Get-Content \'{path}\' -Tail {tail}"'
    return _ssh(cmd, timeout=60) or "(empty or not found)"


@mcp.tool()
def run(command: str) -> str:
    """Run a read-only diagnostic command on the garage laptop (dir, reg query,
    tasklist, findstr, type, PowerShell one-liners). For inspection, not for
    vehicle writes. Anything that changes state should go through a human."""
    return _ssh(command, timeout=60) or "(no output)"


# --- opt-in input tools: gated, and never for use during a flash/coding write ---

def _send(line: str) -> str:
    if not ALLOW_INPUT:
        return ("Input is disabled. Set ISTA_MCP_ALLOW_INPUT=1 to enable it, and "
                "NEVER enable it during a flash / coding / actuator write.")
    tmp = tempfile.mktemp(suffix=".txt")
    pathlib.Path(tmp).write_text(line + "\n")
    _scp(tmp, f"{GARAGE}:{REMOTE_DIR}/action.txt")
    _ssh("schtasks /run /tn IstaInput", timeout=20)
    time.sleep(1.5)
    return f"sent: {line}"


@mcp.tool()
def click(x: int, y: int) -> str:
    """(opt-in) Left-click at screen coordinates. Take a screenshot() first to find
    the target. Do NOT use during a flash/coding/actuator write."""
    return _send(f"CLICK {x} {y}")


@mcp.tool()
def type_text(text: str) -> str:
    """(opt-in) Type text into the currently focused ISTA field (e.g. a VIN)."""
    return _send("TYPE " + text)


@mcp.tool()
def press_key(key: str) -> str:
    """(opt-in) Press a single key: ENTER, TAB or ESC."""
    return _send("KEY " + key)


if __name__ == "__main__":
    mcp.run()
