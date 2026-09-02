# Reads one action from C:\ista-mcp\action.txt and performs it in the interactive
# desktop session, logging to C:\ista-mcp\input.log. Actions:
#   CLICK x y     - left-click at screen pixel coords (relative to the grab.ps1 screenshot)
#   RCLICK x y    - right-click (context menus, e.g. E-Sys 'Edit FDL')
#   DBLCLICK x y  - left double-click (open tree items / files)
#   SCROLL n      - mouse wheel (WHEEL_DELTA units; negative = down)
#   TYPE text     - type into the focused field
#   KEY  ENTER    - ENTER / TAB / ESC
#   UIA  name     - find a control in the ISTA window by name (exact > prefix >
#                   substring, case-insensitive) via UIAutomation and act on it:
#                   Invoke > Select > Toggle > Expand, falling back to a physical
#                   click at its centre. Robust against layout shifts, unlike CLICK.
#   UIALIST [f]   - dump ISTA's actionable controls (buttons, tabs, list/tree items,
#                   links, fields) to C:\ista-mcp\uia.txt, optionally name-filtered.
#                   Read-only - gives the model a menu of real names to UIA-click.
#   PING          - no-op, just logs (used to confirm the task->script path works)
# UIA/UIALIST outcomes are written to C:\ista-mcp\uia.txt for the Mac to pull.
# NOTE: if ISTA runs ELEVATED, UIPI blocks Invoke/clicks (UIALIST still works).
# Fix: elev.ps1 -Mode off, then restart ISTA.
# Coordinate clicks use SendInput with ABSOLUTE normalised coords (0-65535), which is
# DPI-independent and matches grab.ps1's PrimaryScreen.Bounds capture (both DPI-aware).
$ErrorActionPreference = "Stop"
$log = "C:\ista-mcp\input.log"
$uiaOut = "C:\ista-mcp\uia.txt"
function Log($m) { "$(Get-Date -Format s) $m" | Add-Content $log }

try {
  # action.txt may hold SEVERAL lines - they run in order inside this one process,
  # so a popup menu opened by RCLICK survives until the KEY/CLICK that picks from it.
  $actions = @(Get-Content "C:\ista-mcp\action.txt" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  Log ("IN [" + ($actions -join ' | ') + "]")

  # DPI fix (2 Sep 2026): PowerShell is DPI-unaware, so at 125% scaling on a
  # 1920x1080 panel PrimaryScreen.Bounds reported 1536x864 - the capture was the
  # top-left crop and every click landed 1.25x off target. Opt in before any screen call.
  Add-Type -Namespace W -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
  [void][W.Dpi]::SetProcessDPIAware()
  Add-Type -AssemblyName System.Windows.Forms
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $W = $b.Width; $H = $b.Height

  Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Inp {
  [StructLayout(LayoutKind.Sequential)] public struct MI { public int dx; public int dy; public uint data; public uint flags; public uint time; public IntPtr extra; }
  [StructLayout(LayoutKind.Sequential)] public struct IN { public uint type; public MI mi; }
  [DllImport("user32.dll")] public static extern uint SendInput(uint n, IN[] p, int cb);
  const uint MOVE=0x0001, ABS=0x8000, LD=0x0002, LU=0x0004, RD=0x0008, RU=0x0010, WH=0x0800;
  // presses: 1 = left click, 2 = left double-click, -1 = right click
  public static uint Click(int x,int y,int W,int H){ return Press(x,y,W,H,1); }
  public static uint Press(int x,int y,int W,int H,int presses){
    int nx=(int)((double)x*65535/(W-1)), ny=(int)((double)y*65535/(H-1));
    uint down = presses < 0 ? RD : LD, up = presses < 0 ? RU : LU;
    int n = presses < 0 ? 1 : presses;
    // Move first, then pause: Java Swing popup menus and tooltips only arm an item
    // after a hover, so a move+press in one SendInput batch falls through the menu.
    IN[] m=new IN[1]; m[0].type=0; m[0].mi.dx=nx; m[0].mi.dy=ny; m[0].mi.flags=MOVE|ABS;
    uint sent=SendInput(1,m,Marshal.SizeOf(typeof(IN)));
    System.Threading.Thread.Sleep(120);
    IN[] a=new IN[2*n];
    for (int i=0;i<n;i++){ a[2*i].type=0; a[2*i].mi.flags=down; a[2*i+1].type=0; a[2*i+1].mi.flags=up; }
    return sent+SendInput((uint)a.Length,a,Marshal.SizeOf(typeof(IN)));
  }
  public static uint Wheel(int amt){ IN[] a=new IN[1]; a[0].type=0; a[0].mi.data=(uint)amt; a[0].mi.flags=WH; return SendInput(1,a,Marshal.SizeOf(typeof(IN))); }
}
"@

  # ---- UIAutomation helpers (UIA / UIALIST verbs) ----
  $ACTIONABLE = @("Button","TabItem","ListItem","TreeItem","Hyperlink","MenuItem",
                  "ComboBox","CheckBox","RadioButton","Edit","SplitButton","DataItem")

  function Get-AppElements([string]$procMatch = "ISTAGUI") {
    # UIA controls for any app, matched by process-name substring (ISTAGUI, EsysUltra,
    # E-Sys, ...). Works for .NET/WPF apps; a pure-Java app (E-Sys) may expose little
    # unless the Java Access Bridge is on - UIALIST against it is the quick probe.
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    $procs = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*$procMatch*" })
    if (-not $procs) { throw "$procMatch is not running" }
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $wins = @()
    $tops = $root.FindAll([System.Windows.Automation.TreeScope]::Children,
                          [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($w in $tops) { if ($procs.Id -contains $w.Current.ProcessId) { $wins += $w } }
    if (-not $wins) { throw "no top-level window found via UIA for '$procMatch'" }
    $conds = foreach ($t in $ACTIONABLE) {
      New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::$t)
    }
    $or = New-Object System.Windows.Automation.OrCondition([System.Windows.Automation.Condition[]]$conds)
    $els = @()
    foreach ($w in $wins) {
      $found = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $or)
      foreach ($e in $found) { $els += $e }
    }
    return $els
  }

  function Describe($el) {
    $c = $el.Current
    $t = $c.ControlType.ProgrammaticName -replace '^ControlType\.', ''
    $r = $c.BoundingRectangle
    $rect = if ($r.Width -gt 0) { "{0},{1},{2},{3}" -f [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height } else { "offscreen" }
    "{0}`t{1}`t{2}`t{3}`t{4}" -f $t, $c.Name, $c.AutomationId, $rect, $c.IsEnabled
  }

  function Do-Action($el) {
    $c = $el.Current
    foreach ($try in @(
      @{ P = [System.Windows.Automation.InvokePattern]::Pattern;         A = { param($p) $p.Invoke() };  N = "invoked" },
      @{ P = [System.Windows.Automation.SelectionItemPattern]::Pattern;  A = { param($p) $p.Select() };  N = "selected" },
      @{ P = [System.Windows.Automation.TogglePattern]::Pattern;         A = { param($p) $p.Toggle() };  N = "toggled" },
      @{ P = [System.Windows.Automation.ExpandCollapsePattern]::Pattern; A = { param($p) $p.Expand() };  N = "expanded" }
    )) {
      try { $pat = $el.GetCurrentPattern($try.P); & $try.A $pat; return $try.N } catch {}
    }
    try { $pt = $el.GetClickablePoint(); $x = [int]$pt.X; $y = [int]$pt.Y }
    catch { $r = $c.BoundingRectangle; $x = [int]($r.X + $r.Width / 2); $y = [int]($r.Y + $r.Height / 2) }
    $n = [Inp]::Click($x, $y, $W, $H)
    return "clicked centre $x,$y sent=$n"
  }

  foreach ($a in $actions) {
  $parts = $a -split '\s+', 2
  $verb = $parts[0]
  $arg = if ($parts.Count -gt 1) { $parts[1] } else { "" }
  switch ($verb) {
    "PING"   { Log "PING ok screen=${W}x${H}" }
    "CLICK"  { $xy = $arg -split '\s+'; $r = [Inp]::Click([int]$xy[0], [int]$xy[1], $W, $H); Log "CLICK $arg screen=${W}x${H} sent=$r" }
    "RCLICK" { $xy = $arg -split '\s+'; $r = [Inp]::Press([int]$xy[0], [int]$xy[1], $W, $H, -1); Log "RCLICK $arg screen=${W}x${H} sent=$r" }
    "DBLCLICK" { $xy = $arg -split '\s+'; $r = [Inp]::Press([int]$xy[0], [int]$xy[1], $W, $H, 2); Log "DBLCLICK $arg screen=${W}x${H} sent=$r" }
    "SCROLL" { $r = [Inp]::Wheel([int]$arg); Log "SCROLL $arg sent=$r" }
    "TYPE"   { [System.Windows.Forms.SendKeys]::SendWait($arg); Log "TYPE done" }
    "KEY"    { $k = switch ($arg.ToUpper()) { "ENTER" {"{ENTER}"} "TAB" {"{TAB}"} "ESC" {"{ESC}"} default {$arg} }; [System.Windows.Forms.SendKeys]::SendWait($k); Log "KEY $k" }
    "UIALIST" {
      # optional "@proc" first token targets another app (default ISTAGUI)
      $target = "ISTAGUI"
      if ($arg -match '^\s*@(\S+)\s*(.*)$') { $target = $Matches[1]; $arg = $Matches[2] }
      $els = Get-AppElements $target
      $lines = foreach ($el in $els) {
        $d = Describe $el
        if (-not $arg -or $d -like "*$arg*") { $d }
      }
      $lines = @($lines | Where-Object { $_ -notmatch "^\S+`t`t`t" })  # drop no-name no-id noise
      $head = "# app=$target  ControlType`tName`tAutomationId`tX,Y,W,H`tEnabled  ({0} shown)" -f $lines.Count
      Set-Content -LiteralPath $uiaOut -Value (@($head) + ($lines | Select-Object -First 400))
      Log "UIALIST @$target '$arg' -> $($lines.Count) controls"
    }
    "UIA" {
      $target = "ISTAGUI"
      if ($arg -match '^\s*@(\S+)\s*(.*)$') { $target = $Matches[1]; $arg = $Matches[2] }
      if (-not $arg) { throw "UIA needs a control name" }
      $els = Get-AppElements $target
      $usable = @($els | Where-Object { $_.Current.Name })
      $exact  = @($usable | Where-Object { $_.Current.Name -ieq $arg })
      $prefix = @($usable | Where-Object { $_.Current.Name -ilike "$arg*" })
      $contain= @($usable | Where-Object { $_.Current.Name -ilike "*$arg*" })
      $pool = if ($exact) { $exact } elseif ($prefix) { $prefix } else { $contain }
      $pool = @($pool | Sort-Object { -not $_.Current.IsEnabled }, { $_.Current.IsOffscreen })
      if (-not $pool) {
        Set-Content -LiteralPath $uiaOut -Value "NOTFOUND: no control matching '$arg' (try UIALIST)"
        Log "UIA '$arg' -> not found"
      } else {
        $el = $pool[0]
        $how = Do-Action $el
        $msg = "OK: '$($el.Current.Name)' [$(($el.Current.ControlType.ProgrammaticName -replace '^ControlType\.',''))] -> $how"
        if ($pool.Count -gt 1) { $msg += " (of $($pool.Count) matches)" }
        Set-Content -LiteralPath $uiaOut -Value $msg
        Log "UIA '$arg' -> $how"
      }
    }
  }
  Start-Sleep -Milliseconds 350
  }
} catch {
  $err = "ERROR $($_.Exception.Message)"
  Log $err
  try { Set-Content -LiteralPath $uiaOut -Value $err } catch {}
}
