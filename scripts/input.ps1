# Reads one action from C:\ista-mcp\action.txt and performs it in the interactive
# desktop session. Actions:
#   CLICK x y     - left-click at screen coordinates
#   TYPE text     - type text into the focused field
#   KEY  ENTER    - press ENTER / TAB / ESC
#   SCROLL n      - mouse-wheel; negative = down, positive = up (WHEEL_DELTA units)
# Input is gated on the MCP side; this only runs when a task fires it.
$a = (Get-Content "C:\ista-mcp\action.txt" -Raw).Trim()
$parts = $a -split '\s+', 2
$verb = $parts[0]

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class N {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, int dx, int dy, int dwData, int dwExtra);
}
"@

switch ($verb) {
  "CLICK" {
    $xy = $parts[1] -split '\s+'
    [N]::SetCursorPos([int]$xy[0], [int]$xy[1])
    Start-Sleep -Milliseconds 80
    [N]::mouse_event(0x02, 0, 0, 0, 0)   # left down
    [N]::mouse_event(0x04, 0, 0, 0, 0)   # left up
  }
  "SCROLL" {
    [N]::mouse_event(0x0800, 0, 0, [int]$parts[1], 0)   # wheel; dwData signed
  }
  "TYPE" {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.SendKeys]::SendWait($parts[1])
  }
  "KEY" {
    Add-Type -AssemblyName System.Windows.Forms
    $k = switch ($parts[1].ToUpper()) {
      "ENTER" { "{ENTER}" } "TAB" { "{TAB}" } "ESC" { "{ESC}" } default { $parts[1] }
    }
    [System.Windows.Forms.SendKeys]::SendWait($k)
  }
}
