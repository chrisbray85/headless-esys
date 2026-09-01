# Reads one action from C:\ista-mcp\action.txt and performs it in the interactive
# desktop session. Actions: "CLICK x y", "TYPE some text", "KEY ENTER|TAB|ESC".
# Input is gated on the MCP side; this script only runs when a task fires it.
$a = (Get-Content "C:\ista-mcp\action.txt" -Raw).Trim()
$parts = $a -split '\s+', 2
$verb = $parts[0]

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class N {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, int e);
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
