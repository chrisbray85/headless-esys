# Reads one action from C:\ista-mcp\action.txt and performs it in the interactive
# desktop session, logging to C:\ista-mcp\input.log. Actions:
#   CLICK x y   - left-click at screen pixel coords (relative to the grab.ps1 screenshot)
#   SCROLL n    - mouse wheel (WHEEL_DELTA units; negative = down)
#   TYPE text   - type into the focused field
#   KEY  ENTER  - ENTER / TAB / ESC
#   PING        - no-op, just logs (used to confirm the task->script path works)
# Uses SendInput with ABSOLUTE normalised coords (0-65535 across the primary screen),
# which is DPI-independent and matches grab.ps1's PrimaryScreen.Bounds capture.
$ErrorActionPreference = "Stop"
$log = "C:\ista-mcp\input.log"
try {
  $a = (Get-Content "C:\ista-mcp\action.txt" -Raw).Trim()
  "$(Get-Date -Format s) IN [$a]" | Add-Content $log
  $parts = $a -split '\s+', 2
  $verb = $parts[0]

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
  const uint MOVE=0x0001, ABS=0x8000, LD=0x0002, LU=0x0004, WH=0x0800;
  public static uint Click(int x,int y,int W,int H){
    int nx=(int)((double)x*65535/(W-1)), ny=(int)((double)y*65535/(H-1));
    IN[] a=new IN[3];
    a[0].type=0; a[0].mi.dx=nx; a[0].mi.dy=ny; a[0].mi.flags=MOVE|ABS;
    a[1].type=0; a[1].mi.flags=MOVE|ABS; a[1].mi.dx=nx; a[1].mi.dy=ny;
    a[1].mi.flags=LD;
    a[2].type=0; a[2].mi.flags=LU;
    return SendInput(3,a,Marshal.SizeOf(typeof(IN)));
  }
  public static uint Wheel(int amt){ IN[] a=new IN[1]; a[0].type=0; a[0].mi.data=(uint)amt; a[0].mi.flags=WH; return SendInput(1,a,Marshal.SizeOf(typeof(IN))); }
}
"@
  switch ($verb) {
    "PING"   { "$(Get-Date -Format s) PING ok screen=${W}x${H}" | Add-Content $log }
    "CLICK"  { $xy = $parts[1] -split '\s+'; $r = [Inp]::Click([int]$xy[0], [int]$xy[1], $W, $H); "$(Get-Date -Format s) CLICK $($parts[1]) screen=${W}x${H} sent=$r" | Add-Content $log }
    "SCROLL" { $r = [Inp]::Wheel([int]$parts[1]); "$(Get-Date -Format s) SCROLL $($parts[1]) sent=$r" | Add-Content $log }
    "TYPE"   { [System.Windows.Forms.SendKeys]::SendWait($parts[1]); "$(Get-Date -Format s) TYPE done" | Add-Content $log }
    "KEY"    { $k = switch ($parts[1].ToUpper()) { "ENTER" {"{ENTER}"} "TAB" {"{TAB}"} "ESC" {"{ESC}"} default {$parts[1]} }; [System.Windows.Forms.SendKeys]::SendWait($k); "$(Get-Date -Format s) KEY $k" | Add-Content $log }
  }
} catch {
  "$(Get-Date -Format s) ERROR $($_.Exception.Message)" | Add-Content $log
}
