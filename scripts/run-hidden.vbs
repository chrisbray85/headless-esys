' run-hidden.vbs <script.ps1> [args...]
' Runs PowerShell with NO console window. "-WindowStyle Hidden" still flashes a
' black console for a moment, and that flash steals focus from the desktop -
' enough to dismiss a Java popup menu between two helper actions (2 Sep 2026).
Set sh = CreateObject("WScript.Shell")
cmd = "powershell -NoProfile -ExecutionPolicy Bypass -File """ & WScript.Arguments(0) & """"
For i = 1 To WScript.Arguments.Count - 1
  cmd = cmd & " " & WScript.Arguments(i)
Next
sh.Run cmd, 0, True
