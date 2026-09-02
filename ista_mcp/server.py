#!/usr/bin/env python3
"""ISTA-MCP - drive a remote BMW ISTA+ garage laptop from an MCP client.

READ ORDER (fastest first - this is the redesign's core rule):
  1. read_state() / read_doc() - ISTA renders its displayed procedure / fault /
     functional-description content as HTML to %LOCALAPPDATA%\\Temp\\tempWebView.html.
     Reading THAT gives the full text in one round-trip: no OCR, no edge clipping,
     no screenshot loop. read_state() bundles the doc text + one screen frame +
     ISTA process status into a single SSH call.
  2. read_log() / list_sessions() - ISTA + PsdzWebservice logs as text.
  3. screenshot() / latest_frame() - ONLY for what is genuinely pixels: live graphs
     (actuation-test traces), which tab is active, dialog state.

INPUT: click controls BY NAME with click_control() (UIAutomation: Invoke/Select,
coordinate click only as fallback) - list_controls() shows the real names. Raw
coordinate click/type/scroll remain as fallbacks. All input is OPT-IN via
ISTA_MCP_ALLOW_INPUT=1, and input only lands if ISTA runs NON-elevated: Windows
UIPI silently discards injected input into an elevated window. Check/fix with
ista_elevation() - diagnosis does not need admin; only programming/coding does.

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
import base64
import json
import os
import pathlib
import re
import subprocess
import tempfile
import time
from html.parser import HTMLParser

from mcp.server.mcpserver import Image, MCPServer

GARAGE = os.environ.get("ISTA_MCP_SSH", "user@garage-laptop")  # set ISTA_MCP_SSH to your laptop, e.g. user@100.x.y.z
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
    # Capture bytes and decode UTF-8 with replacement: ISTA logs/HTML carry the odd
    # non-UTF-8 byte and text=True would raise UnicodeDecodeError mid-tool. state.ps1
    # forces UTF-8 output; this is the belt-and-braces so nothing ever crashes.
    r = subprocess.run(["ssh", "-n", *SSH_OPTS, GARAGE, cmd],
                       capture_output=True, timeout=timeout)
    out = (r.stdout or b"").decode("utf-8", "replace")
    if r.returncode and r.stderr:
        out += "\n[stderr] " + r.stderr.decode("utf-8", "replace").strip()
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


class _HtmlText(HTMLParser):
    """Minimal HTML -> readable text: block tags become newlines, table cells become
    tab-separated columns, script/style content is dropped. Good enough for ISTA's
    rendered procedure/fault docs; pass raw=True to read_doc() if structure matters."""
    _SKIP = {"script", "style", "head", "title"}
    _BLOCK = {"p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table",
              "section", "article", "ul", "ol", "dl", "dt", "dd", "pre", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag == "br" or tag in self._BLOCK:
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append("\t")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def _html_to_text(markup: str) -> str:
    p = _HtmlText()
    try:
        p.feed(markup)
        p.close()
    except Exception:
        pass  # keep whatever was parsed before the hiccup
    text = "".join(p.out)
    text = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _state(no_frame: bool = False, fresh_ms: int = 2500) -> dict:
    """ONE ssh round-trip: run state.ps1 on the laptop, get back doc HTML + frame +
    ISTA status as a single JSON blob. This is the latency fix - the old loop paid a
    trigger + sleep + scp per read; this pays one multiplexed exec."""
    cmd = (f"powershell -NoProfile -ExecutionPolicy Bypass -File {REMOTE_WIN}\\state.ps1 "
           f"-FreshMs {int(fresh_ms)}")
    if no_frame:
        cmd += " -NoFrame"
    out = _ssh(cmd, timeout=45)
    try:
        return json.loads(out[out.index("{"):out.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        raise RuntimeError(
            "state.ps1 gave no JSON - run setup() to deploy it. Raw output:\n"
            + out[:500])


def _status_line(st: dict) -> str:
    running = st.get("ista_running")
    layer = st.get("runasadmin_layer")
    if not running:
        ista = "not running"
    elif layer:
        # layer set + running => almost certainly elevated => UIPI blocks input.
        # ista_elevation() confirms authoritatively via the token integrity level.
        ista = ("running, likely ELEVATED (RUNASADMIN layer set) - if clicks don't "
                "land, ista_elevation('off') + restart ISTA; confirm with ista_elevation()")
    else:
        ista = "running, no RUNASADMIN layer (input should land)"
    doc_age = st.get("html_ms")
    doc = f"doc text {doc_age / 1000:.0f}s old" if doc_age is not None else "no doc html"
    return f"ISTA {ista} | {doc} | frame: {st.get('frame_src')}"


@mcp.tool()
def read_state(with_frame: bool = True, fresh_ms: int = 2500) -> list:
    """THE primary read: one round-trip returning ISTA's currently displayed document
    text (parsed from ISTA's own rendered HTML - full text, no OCR, no clipping) plus
    one screen frame and ISTA process status. Start every look-at-ISTA step here;
    fall back to screenshot() only for purely graphical detail (live graphs).

    with_frame=False skips the image (fastest, text only). fresh_ms: a stream frame
    younger than this is served as-is; otherwise a fresh one-shot is captured.
    The status line also warns if ISTA is running elevated (= clicks won't land)."""
    st = _state(no_frame=not with_frame, fresh_ms=fresh_ms)
    text = _status_line(st)
    if st.get("html"):
        text += "\n\n--- ISTA displayed document (tempWebView.html) ---\n"
        text += _html_to_text(st["html"])
    else:
        text += "\n\n(no tempWebView.html - ISTA has not rendered a document view yet)"
    parts: list = [text]
    if st.get("frame_b64"):
        parts.append(Image(data=base64.b64decode(st["frame_b64"]), format="jpeg"))
    return parts


@mcp.tool()
def read_doc(raw: bool = False) -> str:
    """Read the full text of whatever document/procedure/fault description ISTA is
    displaying right now, from ISTA's own rendered HTML (tempWebView.html). Instant
    and complete - long lines are NOT clipped at the screen edge like screenshots.
    raw=True returns the untouched HTML (tables/attributes) instead of parsed text."""
    st = _state(no_frame=True)
    if not st.get("html"):
        return (f"{_status_line(st)}\n(no tempWebView.html yet - open a document, "
                "test plan or functional description in ISTA first)")
    body = st["html"] if raw else _html_to_text(st["html"])
    return f"{_status_line(st)}\n\n{body}"


@mcp.tool()
def diagnose() -> str:
    """Pinpoint WHY capture/input is (or isn't) working, in one call. Run this first
    whenever screenshot() returns nothing or clicks don't land - it turns a silent
    failure into a named cause. Checks: a desktop is logged in; the Defender exclusion
    is present (missing => scripts silently quarantined); Windows Task Scheduler is
    actually executing tasks (a pending-reboot limbo can wedge it so /run 'succeeds'
    but nothing runs - the usual reason capture dies after an install); ISTA's process
    + real integrity level (elevated => injected input is blocked by UIPI); and how
    fresh the doc HTML / live stream are."""
    out = _ssh(f"powershell -NoProfile -ExecutionPolicy Bypass -File "
               f"{REMOTE_WIN}\\diagnose.ps1", timeout=45)
    try:
        d = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return ("diagnose.ps1 gave no JSON - run setup() to deploy it. Raw:\n" + out[:600])
    # Guard against a parse error that yields an object without our fields: don't
    # fabricate "everything is broken" from missing keys - say the check didn't run.
    if "scheduler_ok" not in d:
        return ("diagnose.ps1 ran but returned no usable data (missing expected fields) "
                "- it likely errored on the laptop. Re-run setup() to redeploy it. Raw:\n"
                + out[:600])

    problems, notes = [], []
    if d.get("desktop_session") is False:
        problems.append("NO desktop session logged in - /it capture tasks can't reach a "
                        "desktop. Log in at the console (auto-login should handle this).")
    if d.get("defender_excluded") is False:
        problems.append("Defender exclusion for C:\\ista-mcp is MISSING - grab/input.ps1 "
                        "get silently quarantined as malicious. Re-run setup().")
    if d.get("on_battery") and d.get("scheduler_ok") is False:
        problems.append("Laptop is ON BATTERY and the scheduler probe didn't run - tasks "
                        "registered with the default 'don't start on batteries' condition "
                        "sit in Queued. Re-run setup() (it clears that condition) or plug in.")
    elif d.get("scheduler_ok") is False:
        msg = ("Task Scheduler is NOT executing tasks (a throwaway SYSTEM task didn't "
               "run) - capture/input both ride it, so both are dead.")
        if d.get("pending_reboot"):
            msg += (f" Pending reboot detected (pending_files={d.get('pending_files')}) "
                    "- REBOOT the laptop to clear it; capture should work after.")
        else:
            msg += " No pending-reboot flag; try rebooting the laptop anyway."
        problems.append(msg)
    if d.get("ista_running") and d.get("ista_integrity") in ("high", "system"):
        notes.append("ISTA is elevated - fine, the IstaInput task runs elevated too "
                     "(/rl HIGHEST) so clicks still land past UIPI. If they don't, "
                     "fallback is ista_elevation('off') + restart ISTA.")
    if not d.get("ista_running"):
        notes.append("ISTA (ISTAGUI.exe) is not running.")

    verdict = ("All capture/input prerequisites look good." if not problems
               else "BLOCKERS found:\n  - " + "\n  - ".join(problems))
    if notes:
        verdict += "\nNotes:\n  - " + "\n  - ".join(notes)
    doc = d.get("doc_age_ms")
    stream = d.get("live_stream_ms")
    facts = (f"desktop={d.get('desktop_session')} defender_excluded={d.get('defender_excluded')} "
             f"scheduler_ok={d.get('scheduler_ok')} on_battery={d.get('on_battery')} pending_reboot={d.get('pending_reboot')} "
             f"ista={d.get('ista_integrity') if d.get('ista_running') else 'not running'} "
             f"doc={'%.0fs' % (doc / 1000) if doc is not None else 'none'} "
             f"stream={'%.0fs' % (stream / 1000) if stream is not None else 'off'}\n"
             f"sessions: {', '.join(d.get('sessions') or []) or '(none parsed)'}")
    return f"{verdict}\n\n{facts}"


@mcp.tool()
def setup() -> str:
    """One-time install: copy the helper scripts to the garage laptop and register
    the scheduled tasks that let capture and input run in the interactive desktop
    session. Registers IstaGrab (JPEG one-shot), IstaGrabPng (lossless PNG fallback),
    IstaGrabLoop (continuous near-live stream) and IstaInput. Run this once before
    first use, and again after updating grab.ps1 / input.ps1."""
    _ssh(f'if not exist "{REMOTE_WIN}" mkdir "{REMOTE_WIN}"')
    # Windows Defender flags screen-capture + SendInput scripts as malicious
    # ("ScriptContainedMaliciousContent") and silently blocks them - screenshots
    # then just never appear. ISTA's own dirs are already excluded; add ours too.
    # Best-effort: needs an admin SSH token (OpenSSH gives one to an admin user);
    # a non-admin login just gets a warning here and can add it by hand.
    defender = _ssh(
        f'powershell -NoProfile -Command "try {{ Add-MpPreference -ExclusionPath '
        f"'{REMOTE_WIN}' -ErrorAction Stop; 'defender-exclusion-ok' }} catch "
        f"{{ 'defender-exclusion-FAILED: ' + $_.Exception.Message }}\"")
    for f in ("grab.ps1", "input.ps1", "state.ps1", "elev.ps1", "diagnose.ps1",
              "run-hidden.vbs"):
        _scp(str(SCRIPTS / f), f"{GARAGE}:{REMOTE_DIR}/{f}")
    # wscript + run-hidden.vbs: no console window at all (a hidden powershell still
    # flashes one, which steals focus and kills Java popup menus mid-sequence).
    hidden = f"wscript.exe //B //Nologo {REMOTE_WIN}\\run-hidden.vbs"
    ps = f"{hidden} {REMOTE_WIN}\\grab.ps1"
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
    ips = f"{hidden} {REMOTE_WIN}\\input.ps1"
    # /rl HIGHEST => the input task runs ELEVATED (high integrity), so injected clicks
    # land into an elevated ISTA window instead of being silently dropped by UIPI -
    # no ISTA restart needed. This only works because the SSH login is an admin (Task
    # Scheduler elevates the task without a UAC prompt); a non-admin login would fall
    # back to needing ista_elevation('off'). Capture tasks stay Limited - they don't
    # need elevation, only the interactive session.
    inp = _ssh(f'schtasks /create /tn IstaInput /tr "{ips}" /sc once /st 23:59 '
               f'/it /rl HIGHEST /f')
    # schtasks /create leaves the default "don't start on batteries" condition set.
    # The garage laptop runs unplugged at the car, and every task then just sits
    # in Queued - capture and input both silently die (2 Sep 2026). Clear it.
    names = ",".join(f"'{t}'" for t in [*tasks, "IstaInput"])
    _ssh("powershell -NoProfile -Command \"$s=New-ScheduledTaskSettingsSet "
         "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
         "-ExecutionTimeLimit (New-TimeSpan -Hours 72); "
         f"foreach($t in {names}){{Set-ScheduledTask -TaskName $t -Settings $s | Out-Null}}\"")
    return (f"Defender exclusion: {defender}. Installed grab.ps1 + input.ps1 + "
            "state.ps1 + elev.ps1 + diagnose.ps1 and registered IstaGrab (JPEG "
            "one-shot), IstaGrabPng (PNG fallback), IstaGrabLoop (stream) and "
            f"IstaInput [elevated: {inp.strip()[:60]}]. read_state()/read_doc(), "
            "screenshot(), list_controls()/click_control() and ista_elevation() are "
            "ready. If capture ever comes back empty, call diagnose() - it names the "
            "cause. Input runs elevated so clicks land even into an elevated ISTA; "
            "if they still don't, ista_elevation('off') + restart ISTA is the "
            "fallback. Capture/input run via /it scheduled tasks in the console "
            "session, so a desktop must be logged in (a wedged Task Scheduler after "
            "an install = reboot; diagnose() will say so).")


@mcp.tool()
def screenshot(fmt: str = "jpg") -> Image:
    """Capture the garage laptop's screen right now (one-shot). Reach for this ONLY
    for genuinely graphical content: live graphs (actuation-test traces), which tab
    is highlighted, dialog state. For anything textual - fault descriptions, test
    plans, procedures - read_state()/read_doc() return the full text faster with no
    OCR and no edge clipping.

    fmt="jpg" (default) returns a compressed JPEG - a few tens of KB, best over a
    hotspot. fmt="png" returns the lossless ~600 KB frame when you need pixel detail.

    For the BMW coding apps (EsysUltra, E-Sys) this IS the read path: they're Java
    UIs with no tempWebView.html and near-empty UIA, so you read the screen visually
    from this frame and act with coordinate click()/type_text(). Keep the app
    maximised so it fills the 1920x1080 capture (native, DPI-aware).

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
    raise RuntimeError("screenshot: no frame produced. Call diagnose() to find out why "
                       "- the usual causes are a wedged Task Scheduler (pending reboot), "
                       "a missing Defender exclusion, or no desktop logged in.")


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


# --- input + UIA tools. Real input is gated (ISTA_MCP_ALLOW_INPUT=1) and never
# --- for use during a flash/coding write; UIALIST is read-only and ungated.

def _action(line: str, want_result: bool = False, wait: float = 12.0) -> str:
    """Ship one action line to the laptop and trigger the IstaInput task (it runs in
    the interactive desktop session). For UIA verbs the script writes its outcome to
    uia.txt; want_result waits for that file to change and returns its content."""
    tmp = tempfile.mktemp(suffix=".txt")
    pathlib.Path(tmp).write_text(line + "\n")
    before = _remote_ticks(f"{REMOTE_WIN}\\uia.txt") if want_result else 0
    _scp(tmp, f"{GARAGE}:{REMOTE_DIR}/action.txt")
    _ssh("schtasks /run /tn IstaInput", timeout=20)
    if not want_result:
        time.sleep(1.5)
        return f"sent: {line}"
    if not _wait_fresh(f"{REMOTE_WIN}\\uia.txt", before, timeout=wait, initial=1.2):
        return (f"sent: {line} - but no result appeared in uia.txt within {wait}s "
                "(big UIA trees can be slow; read it with "
                "run('type C:\\\\ista-mcp\\\\uia.txt'))")
    data = _pull("uia.txt")
    return data.decode("utf-8", "replace").strip() if data else "(uia.txt empty)"


def _send(line: str) -> str:
    if not ALLOW_INPUT:
        return ("Input is disabled. Set ISTA_MCP_ALLOW_INPUT=1 to enable it, and "
                "NEVER enable it during a flash / coding / actuator write.")
    return _action(line)


@mcp.tool()
def list_controls(name_filter: str = "", app: str = "ISTAGUI") -> str:
    """List an app's actionable UI controls (buttons, tabs, list/tree items, links,
    fields) by their real UIAutomation names - read-only, works even while the app
    runs elevated. Use it to find the exact name for click_control() instead of
    hunting pixel coordinates. Optional name_filter narrows the list.

    app is a process-name substring: "ISTAGUI" (default, ISTA+), "EsysUltra" or
    "E-Sys" for BMW coding. This is also the probe for whether an app is UIA-driveable
    at all - a WPF/.NET app (ISTA, EsysUltra) lists richly; a pure-Java app (E-Sys)
    may show little, in which case fall back to screenshot() + coordinate click().
    Columns: ControlType, Name, AutomationId, X,Y,W,H, Enabled."""
    line = f"UIALIST @{app}" + (f" {name_filter}" if name_filter else "")
    return _action(line, want_result=True, wait=20.0)


@mcp.tool()
def click_control(name: str, app: str = "ISTAGUI") -> str:
    """(opt-in) Act on a control BY NAME via UIAutomation - the robust alternative to
    coordinate click(). Matching is case-insensitive: exact, then prefix, then
    substring (list_controls() shows the real names). Uses the control's own
    Invoke/Select/Toggle/Expand pattern, falling back to a physical click at its
    centre. app is a process-name substring: "ISTAGUI" (default), "EsysUltra", etc.

    The IstaInput task runs elevated (/rl HIGHEST), so this lands even into an
    elevated window. If nothing responds, run diagnose() (usually a wedged scheduler).

    HARD RULE for BMW coding (EsysUltra/E-Sys): only click READ/navigate controls
    autonomously. Anything that WRITES to the car - code / program / flash / FDL
    write / VCM - stays human-confirmed. Never click it during an active write."""
    if not ALLOW_INPUT:
        return ("Input is disabled. Set ISTA_MCP_ALLOW_INPUT=1 to enable it, and "
                "NEVER enable it during a flash / coding / actuator write.")
    return _action(f"UIA @{app} {name}", want_result=True)


@mcp.tool()
def ista_elevation(mode: str = "status") -> str:
    """Manage WHY clicks do or don't land. ISTA set to always-run-as-admin means
    Windows UIPI silently discards our injected input (screenshots still work, so
    failures look like ignored clicks). Diagnosis needs no admin; programming does.

    mode="status" - show the RUNASADMIN layer flag + whether the running ISTA is
                    elevated. mode="off" - strip the flag so the NEXT ISTA launch
                    accepts input (restart ISTA to apply). mode="on" - restore
                    always-as-admin for a programming/coding session."""
    if mode not in ("status", "off", "on"):
        return "mode must be status, off or on"
    return _ssh(f"powershell -NoProfile -ExecutionPolicy Bypass -File "
                f"{REMOTE_WIN}\\elev.ps1 -Mode {mode}", timeout=30) or "(no output)"


@mcp.tool()
def click(x: int, y: int) -> str:
    """(opt-in) Left-click at screen coordinates - the PRIMARY way to drive the BMW
    coding apps EsysUltra and E-Sys, which are Java (Swing/JavaFX) and expose little
    to UIAutomation. Flow: screenshot(), read the frame visually, pick the pixel,
    click. Coordinates are screen pixels in the 1920x1080 capture (native, DPI-aware; UIA coords match 1:1). Runs elevated so it lands
    even in an elevated window.

    HARD RULE (BMW coding writes to the car - a bad write bricks an ECU): only click
    READ / navigate controls autonomously (Read FA/VO, Read SVT, open the FDL editor,
    read DTCs/NCD). NEVER autonomously click a WRITE-to-car action - "Code FDL", any
    VO/FA write, or TAL execute/flash - those stay human-confirmed, and EsysUltra's
    Full Backup must run first. Never click anything during an active flash/write."""
    return _send(f"CLICK {x} {y}")


@mcp.tool()
def input_sequence(actions: list[str]) -> str:
    """(opt-in) Run several input actions in ONE helper pass, ~350 ms apart, so a
    popup menu opened by one step is still open for the next. Each item is a raw
    verb line: "CLICK x y", "RCLICK x y", "DBLCLICK x y", "SCROLL n", "TYPE text",
    "KEY {DOWN}{DOWN}{ENTER}" (SendKeys syntax; ENTER/TAB/ESC also accepted).
    Example - E-Sys context menu, 2nd item: ["RCLICK 452 710", "KEY {DOWN}{DOWN}{ENTER}"].
    Same HARD RULE as click(): never a write-to-car item."""
    return _send("\n".join(a.strip() for a in actions if a.strip()))


@mcp.tool()
def right_click(x: int, y: int) -> str:
    """(opt-in) Right-click at screen coordinates - opens context menus, which is how
    E-Sys/EsysUltra reach "Edit FDL" on a CAFD in the SVT tree. Same coordinate space
    and HARD RULE as click(): read/navigate menu items only; any code/flash item in
    the menu stays human-confirmed."""
    return _send(f"RCLICK {x} {y}")


@mcp.tool()
def double_click(x: int, y: int) -> str:
    """(opt-in) Left double-click at screen coordinates - open a tree item or a file
    in a Java Swing list. Same coordinate space and HARD RULE as click()."""
    return _send(f"DBLCLICK {x} {y}")


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
