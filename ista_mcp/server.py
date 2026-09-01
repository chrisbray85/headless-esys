#!/usr/bin/env python3
"""ISTA-MCP - drive a remote BMW ISTA+ garage laptop from an MCP client.

The read-only tools (screenshot, latest_frame, read_log, list_sessions, run) are the
safe core and are built on primitives proven by hand over SSH + Tailscale. The input
tools (click, type_text, press_key, scroll) are OPT-IN via ISTA_MCP_ALLOW_INPUT=1.

HARD RULE: never enable input during a flash / coding / actuator write on a live
car. Observe freely; any action that changes vehicle state stays human-confirmed.

Screen capture (see scripts/grab.ps1):
  * screenshot()   - reliable one-shot. Triggers the IstaGrab task, waits for a fresh
                     frame, pulls it back. Defaults to a compressed JPEG (~tens of KB);
                     fmt="png" gives the lossless ~600 KB fallback.
  * start_stream() - starts a continuous capture loop in the interactive desktop
                     session that writes the newest frame to C:\\ista-mcp\\live.jpg.
  * latest_frame() - the fast, near-live path: one pull of live.jpg, no scheduler
                     trigger and no fixed wait. Falls back to screenshot() if no
                     stream is running.
  * stop_stream()  - stops the loop (saves hotspot bandwidth + laptop CPU).

All ssh/scp calls reuse a single multiplexed SSH connection (ControlMaster), so the
per-frame TCP+SSH handshake cost - which dominates over a high-latency hotspot - is
paid once, not on every frame.
"""
import json
import os
import pathlib
import subprocess
import tempfile
import time

from mcp.server.mcpserver import Image, MCPServer

GARAGE = os.environ.get("ISTA_MCP_SSH", "user@100.x.y.z")
REMOTE_DIR = "C:/ista-mcp"                 # scp target (Windows OpenSSH takes '/')
REMOTE_WIN = REMOTE_DIR.replace("/", "\\")  # C:\ista-mcp - for schtasks / cmd builtins
ISTA_LOGS = r"C:\ProgramData\BMW\ISPI\Logs\TRIC\ISTA"
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
ALLOW_INPUT = os.environ.get("ISTA_MCP_ALLOW_INPUT") == "1"

# Reuse one SSH connection across every ssh/scp call. Over a phone hotspot the
# repeated handshakes were a big slice of the old 10-15 s round-trip; ControlMaster
# opens the tunnel once and keeps it warm for 2 min.
_CM_PATH = os.path.expanduser("~/.ssh/cm-ista-%C")
try:
    os.makedirs(os.path.expanduser("~/.ssh"), mode=0o700, exist_ok=True)
except OSError:
    pass
SSH_OPTS = [
    "-o", "ConnectTimeout=10",
    "-o", "BatchMode=yes",
    "-o", "ControlMaster=auto",
    "-o", f"ControlPath={_CM_PATH}",
    "-o", "ControlPersist=120",
]

mcp = MCPServer("ista-garage")


def _ssh(cmd: str, timeout: int = 40) -> str:
    r = subprocess.run(["ssh", "-n", *SSH_OPTS, GARAGE, cmd],
                       capture_output=True, text=True, timeout=timeout)
    out = r.stdout or ""
    if r.returncode and r.stderr:
        out += f"\n[stderr] {r.stderr.strip()}"
    return out.strip()


def _scp(src: str, dst: str, timeout: int = 30, retries: int = 1) -> None:
    last = None
    for attempt in range(retries + 1):
        try:
            subprocess.run(["scp", *SSH_OPTS, src, dst], check=True,
                           capture_output=True, text=True, timeout=timeout)
            return
        except subprocess.CalledProcessError as e:  # transient over a flaky hotspot
            last = e
            if attempt < retries:
                time.sleep(0.3)
    raise last


def _pull(remote_name: str, timeout: int = 30) -> bytes | None:
    """scp a file back from the laptop and return its bytes, or None if absent."""
    suffix = os.path.splitext(remote_name)[1] or ".bin"
    local = tempfile.mktemp(suffix=suffix)
    try:
        _scp(f"{GARAGE}:{REMOTE_DIR}/{remote_name}", local, timeout=timeout)
    except Exception:
        return None
    try:
        return pathlib.Path(local).read_bytes()
    finally:
        try:
            os.unlink(local)
        except OSError:
            pass


def _remote_ticks(win_path: str) -> int:
    """LastWriteTimeUtc of a remote file in .NET ticks, or 0 if it doesn't exist.
    Used to wait for a genuinely new frame instead of a blind fixed sleep."""
    cmd = (f'powershell -NoProfile -Command "try {{ (Get-Item -LiteralPath '
           f"'{win_path}').LastWriteTimeUtc.Ticks }} catch {{ 0 }}\"")
    out = _ssh(cmd, timeout=15).strip()
    try:
        return int(out.split()[0]) if out else 0
    except (ValueError, IndexError):
        return 0


def _wait_fresh(win_path: str, before: int, timeout: float = 8.0,
                initial: float = 1.0, interval: float = 0.6) -> bool:
    """Give the capture a moment, then poll until the frame is newer than `before`."""
    time.sleep(initial)
    end = time.time() + timeout
    while time.time() < end:
        if _remote_ticks(win_path) > before:
            return True
        time.sleep(interval)
    return False


@mcp.tool()
def setup() -> str:
    """One-time install: copy the helper scripts to the garage laptop and register
    the scheduled tasks that let capture and input run in the interactive desktop
    session. Registers IstaGrab (JPEG one-shot), IstaGrabPng (lossless PNG fallback),
    IstaGrabLoop (continuous near-live stream) and IstaInput. Run this once before
    first use, and again after updating grab.ps1 / input.ps1."""
    _ssh(f'if not exist "{REMOTE_WIN}" mkdir "{REMOTE_WIN}"')
    for f in ("grab.ps1", "input.ps1"):
        _scp(str(SCRIPTS / f), f"{GARAGE}:{REMOTE_DIR}/{f}")
    ps = (f"powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass "
          f"-File {REMOTE_WIN}\\grab.ps1")
    tasks = {
        "IstaGrab": f"{ps} -Format jpg -Out {REMOTE_WIN}\\screen.jpg "
                    f"-ConfigFile {REMOTE_WIN}\\stream.cfg",
        "IstaGrabPng": f"{ps} -Format png -Out {REMOTE_WIN}\\screen.png",
        "IstaGrabLoop": f"{ps} -Loop -Format jpg -Out {REMOTE_WIN}\\live.jpg "
                        f"-Stop {REMOTE_WIN}\\grab.stop "
                        f"-ConfigFile {REMOTE_WIN}\\stream.cfg -MaxSeconds 1800",
    }
    for tn, tr in tasks.items():
        _ssh(f'schtasks /create /tn {tn} /tr "{tr}" /sc once /st 23:59 /it /f')
    ips = (f"powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass "
           f"-File {REMOTE_WIN}\\input.ps1")
    _ssh(f'schtasks /create /tn IstaInput /tr "{ips}" /sc once /st 23:59 /it /f')
    return ("Installed grab.ps1 + input.ps1 and registered IstaGrab (JPEG one-shot), "
            "IstaGrabPng (PNG fallback), IstaGrabLoop (stream) and IstaInput. "
            "screenshot(), start_stream()/latest_frame() and input are ready.")


@mcp.tool()
def screenshot(fmt: str = "jpg") -> Image:
    """Capture the garage laptop's screen right now (one-shot) - i.e. whatever ISTA
    is showing. Use it to read fault memory, test-plan results, graphs and dialogs.

    fmt="jpg" (default) returns a compressed JPEG - a few tens of KB, best over a
    hotspot. fmt="png" returns the lossless ~600 KB frame when you need pixel detail.

    For watching ISTA fluidly (many frames), call start_stream() once and then
    latest_frame() repeatedly - that path skips the scheduler trigger and the wait."""
    want_png = str(fmt).lower() in ("png", "p")
    if want_png:
        task, candidates = "IstaGrabPng", [("screen.png", "png")]
    else:
        # Prefer the new JPEG; fall back to screen.png so this keeps working against a
        # laptop still running the older PNG-only grab.ps1 (setup() not yet re-run).
        task, candidates = "IstaGrab", [("screen.jpg", "jpeg"), ("screen.png", "png")]

    primary = candidates[0][0]
    before = _remote_ticks(f"{REMOTE_WIN}\\{primary}")
    run_out = _ssh(f"schtasks /run /tn {task}", timeout=20)
    if "ERROR" in run_out.upper() and want_png:
        # Old deployment without IstaGrabPng -> use the JPEG task, take screen.png.
        _ssh("schtasks /run /tn IstaGrab", timeout=20)
        candidates = [("screen.png", "png"), ("screen.jpg", "jpeg")]
        before = 0

    _wait_fresh(f"{REMOTE_WIN}\\{candidates[0][0]}", before, timeout=8.0)
    for name, imgfmt in candidates:
        data = _pull(name)
        if data:
            return Image(data=data, format=imgfmt)

    # Last-ditch: honour the original blind-wait behaviour before giving up.
    time.sleep(3)
    for name, imgfmt in candidates:
        data = _pull(name)
        if data:
            return Image(data=data, format=imgfmt)
    raise RuntimeError("screenshot: no frame produced - is a desktop session logged "
                       "in, and has setup() been run on this laptop?")


@mcp.tool()
def start_stream(quality: int = 55, interval_ms: int = 700, scale: float = 1.0,
                 max_seconds: int = 1800) -> str:
    """Start a continuous capture loop in the interactive desktop session. It writes
    the newest compressed frame to C:\\ista-mcp\\live.jpg every ~interval_ms; the Mac
    then grabs the latest one with latest_frame() - no per-frame scheduler trigger and
    no fixed wait, so watching ISTA is far more fluid.

    Turn the tunables down on a weak hotspot: quality=40 and scale=0.75 typically
    halves the per-frame bytes again while ISTA's large UI text stays readable. The
    loop auto-stops after max_seconds as a safety cap; call stop_stream() when done
    to stop using bandwidth and CPU. Retuning while a stream runs is live - just call
    start_stream() again with new values."""
    cfg = {"Quality": int(quality), "IntervalMs": int(interval_ms),
           "Scale": float(scale), "MaxSeconds": int(max_seconds)}
    tmp = tempfile.mktemp(suffix=".cfg")
    pathlib.Path(tmp).write_text(json.dumps(cfg))
    try:
        _scp(tmp, f"{GARAGE}:{REMOTE_DIR}/stream.cfg")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    _ssh(f"if exist {REMOTE_WIN}\\grab.stop del /f /q {REMOTE_WIN}\\grab.stop")
    out = _ssh("schtasks /run /tn IstaGrabLoop", timeout=20)
    if "ERROR" in out.upper():
        return (f"Could not start the stream: {out.strip()}\n"
                "Run setup() first - it registers the IstaGrabLoop task.")
    return (f"Streaming to live.jpg with {cfg}. Pull frames with latest_frame(); "
            f"stop_stream() when done. Auto-stops after {max_seconds}s.")


@mcp.tool()
def latest_frame() -> Image:
    """Return the most recent frame from a running capture loop (start_stream()).
    This is the fast, near-live path: a single pull of C:\\ista-mcp\\live.jpg with no
    scheduler trigger and no fixed delay. If no stream is running (live.jpg absent),
    it transparently falls back to a one-shot screenshot()."""
    data = _pull("live.jpg")
    if data:
        return Image(data=data, format="jpeg")
    return screenshot("jpg")


@mcp.tool()
def stop_stream() -> str:
    """Stop the continuous capture loop started by start_stream(). Drops a stop
    sentinel (the loop exits within one interval and cleans up live.jpg) and ends the
    task as a backstop. Do this when you're done watching to stop using hotspot
    bandwidth and laptop CPU."""
    _ssh(f"echo stop> {REMOTE_WIN}\\grab.stop")
    _ssh("schtasks /end /tn IstaGrabLoop")
    _ssh(f"if exist {REMOTE_WIN}\\live.jpg del /f /q {REMOTE_WIN}\\live.jpg")
    _ssh(f"if exist {REMOTE_WIN}\\live.jpg.tmp del /f /q {REMOTE_WIN}\\live.jpg.tmp")
    return "Stream stopped."


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


@mcp.tool()
def scroll(notches: int = -3) -> str:
    """(opt-in) Mouse-wheel scroll the window under the cursor. Negative scrolls
    down, positive up; ~3 notches is a few lines. Use when an ISTA test-plan panel
    clips its text, then screenshot() again to read the rest."""
    return _send(f"SCROLL {notches * 120}")


if __name__ == "__main__":
    mcp.run()
