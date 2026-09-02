# caltarget.ps1 - on-screen calibration target for capture + click self-test.
#
# Shows a full-screen black window with five large numbered buttons (four corners
# and the centre). It writes, to C:\ista-mcp\cal.txt:
#   SCREEN <w> <h>          physical pixels, DPI-aware (what grab.ps1 must match)
#   TARGET <n> <x> <y>      the centre of each button, in screen pixels
#   HIT <n> <x> <y>         appended when a button is clicked (x,y = cursor position)
# It closes itself when all five are hit, when the Close button is pressed, or after
# -Seconds (default 90). calibrate() in server.py drives it: launch, read TARGETs,
# click each one, read HITs, compare.
param([int]$Seconds = 90, [string]$Out = "C:\ista-mcp\cal.txt")

Add-Type -Namespace W -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[void][W.Dpi]::SetProcessDPIAware()
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$W = $b.Width; $H = $b.Height
Set-Content -LiteralPath $Out -Value "SCREEN $W $H"

$f = New-Object System.Windows.Forms.Form
$f.FormBorderStyle = 'None'; $f.StartPosition = 'Manual'
$f.Bounds = $b; $f.TopMost = $true; $f.BackColor = 'Black'

$lbl = New-Object System.Windows.Forms.Label
$lbl.Text = "headless-esys calibration target  $W x $H  - click the five numbers"
$lbl.ForeColor = 'White'; $lbl.Font = New-Object System.Drawing.Font('Segoe UI', 20)
$lbl.AutoSize = $true; $lbl.Location = New-Object System.Drawing.Point(([int]($W/2) - 420), 20)
$f.Controls.Add($lbl)

$size = 140
$spots = @(
  @{ n = 1; x = [int]($W * 0.10); y = [int]($H * 0.12) },
  @{ n = 2; x = [int]($W * 0.90); y = [int]($H * 0.12) },
  @{ n = 3; x = [int]($W * 0.50); y = [int]($H * 0.50) },
  @{ n = 4; x = [int]($W * 0.10); y = [int]($H * 0.88) },
  @{ n = 5; x = [int]($W * 0.90); y = [int]($H * 0.88) }
)
$script:hits = 0
foreach ($s in $spots) {
  Add-Content -LiteralPath $Out -Value ("TARGET {0} {1} {2}" -f $s.n, $s.x, $s.y)
  $btn = New-Object System.Windows.Forms.Button
  $btn.Text = "$($s.n)"; $btn.Font = New-Object System.Drawing.Font('Segoe UI', 48, [System.Drawing.FontStyle]::Bold)
  $btn.Size = New-Object System.Drawing.Size($size, $size)
  $btn.Location = New-Object System.Drawing.Point(($s.x - [int]($size/2)), ($s.y - [int]($size/2)))
  $btn.BackColor = 'Orange'; $btn.ForeColor = 'Black'; $btn.Tag = $s.n
  $btn.Add_Click({
    $p = [System.Windows.Forms.Cursor]::Position
    Add-Content -LiteralPath $Out -Value ("HIT {0} {1} {2}" -f $this.Tag, $p.X, $p.Y)
    $this.BackColor = 'LimeGreen'; $this.Enabled = $false
    $script:hits++
    if ($script:hits -ge 5) { Add-Content -LiteralPath $Out -Value "DONE"; $this.FindForm().Close() }
  })
  $f.Controls.Add($btn)
}
$close = New-Object System.Windows.Forms.Button
$close.Text = 'Close'; $close.Size = New-Object System.Drawing.Size(160, 60)
$close.Location = New-Object System.Drawing.Point(([int]($W/2) - 80), ($H - 100))
$close.BackColor = 'Gray'; $close.Add_Click({ Add-Content -LiteralPath $Out -Value "CLOSED"; $this.FindForm().Close() })
$f.Controls.Add($close)

$t = New-Object System.Windows.Forms.Timer; $t.Interval = $Seconds * 1000
$t.Add_Tick({ Add-Content -LiteralPath $Out -Value "TIMEOUT"; $f.Close() }); $t.Start()
[void]$f.ShowDialog()
