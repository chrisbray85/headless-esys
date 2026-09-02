# grab.ps1 - screen capture for ISTA-MCP, run in the interactive desktop session.
#
# Two modes:
#   one-shot (default) : capture a single frame to -Out, then exit.
#   loop  (-Loop)      : capture continuously to -Out (atomic writes) until a stop
#                        sentinel appears or -MaxSeconds elapses. The Mac side then
#                        just pulls the newest -Out on demand (latest_frame()) - no
#                        per-frame scheduler trigger, no fixed wait.
#
# Defaults to a COMPRESSED JPEG (~tens of KB) instead of the old ~600 KB PNG. That
# alone is the biggest win over a bandwidth-tight phone hotspot. Pass -Format png for
# a lossless fallback (still atomic, still fast to trigger).
#
# Tunables (Quality / IntervalMs / Scale / MaxSeconds) can be overridden live from
# -ConfigFile (a tiny JSON file), so start_stream() can retune a *running* loop
# without re-registering the scheduled task.
param(
  [string]$Out        = "C:\ista-mcp\screen.jpg",
  [ValidateSet("jpg","png")][string]$Format = "jpg",
  [int]$Quality       = 55,       # JPEG quality 1-100 (ignored for png)
  [double]$Scale      = 1.0,      # 1.0 = native res; 0.75 = 75% on each axis
  [switch]$Loop,
  [int]$IntervalMs    = 700,      # loop: target gap between frames
  [int]$MaxSeconds    = 1800,     # loop: hard safety cap, auto-stops the stream
  [string]$Stop       = "C:\ista-mcp\grab.stop",
  [string]$ConfigFile = ""
)

$ErrorActionPreference = "Stop"
$log = "C:\ista-mcp\grab.log"
function Log($m) { try { "$(Get-Date -Format s) $m" | Add-Content -LiteralPath $log } catch {} }

# DPI fix (2 Sep 2026): PowerShell is DPI-unaware, so at 125% scaling on a
# 1920x1080 panel PrimaryScreen.Bounds reported 1536x864 - the capture was the
# top-left crop and every click landed 1.25x off target. Opt in before any screen call.
Add-Type -Namespace W -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[void][W.Dpi]::SetProcessDPIAware()
Add-Type -AssemblyName System.Windows.Forms,System.Drawing

# Resolve the JPEG encoder once (reused every frame in loop mode).
$jpegCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
             Where-Object { $_.MimeType -eq 'image/jpeg' } | Select-Object -First 1

# Live-tunable knobs, overridable from the JSON config each iteration.
function Read-Config {
  param($path)
  if (-not $path -or -not (Test-Path -LiteralPath $path)) { return }
  try {
    $c = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if ($null -ne $c.Quality)    { $script:Quality    = [int]$c.Quality }
    if ($null -ne $c.Scale)      { $script:Scale      = [double]$c.Scale }
    if ($null -ne $c.IntervalMs) { $script:IntervalMs = [int]$c.IntervalMs }
    if ($null -ne $c.MaxSeconds) { $script:MaxSeconds = [int]$c.MaxSeconds }
  } catch { Log "config read error: $($_.Exception.Message)" }
}

function Save-Frame {
  param($path)
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $shot = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
  $g = [System.Drawing.Graphics]::FromImage($shot)
  try { $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size) }
  finally { $g.Dispose() }

  $img = $shot
  $scaled = $null
  if ($Scale -gt 0 -and $Scale -ne 1.0) {
    $nw = [Math]::Max(1, [int]($b.Width  * $Scale))
    $nh = [Math]::Max(1, [int]($b.Height * $Scale))
    $scaled = New-Object System.Drawing.Bitmap($nw, $nh)
    $gs = [System.Drawing.Graphics]::FromImage($scaled)
    $gs.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    try { $gs.DrawImage($shot, 0, 0, $nw, $nh) } finally { $gs.Dispose() }
    $img = $scaled
  }

  $tmp = "$path.tmp"
  try {
    if ($Format -eq "png") {
      $img.Save($tmp, [System.Drawing.Imaging.ImageFormat]::Png)
    } else {
      $q = [Math]::Max(1, [Math]::Min(100, $Quality))
      $eps = New-Object System.Drawing.Imaging.EncoderParameters(1)
      $eps.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
                        [System.Drawing.Imaging.Encoder]::Quality, [long]$q)
      $img.Save($tmp, $jpegCodec, $eps)
      $eps.Dispose()
    }
  } finally {
    if ($scaled) { $scaled.Dispose() }
    $shot.Dispose()
  }

  # Atomic publish: the Mac must never scp a half-written file. Replace() is atomic
  # (ReplaceFile API); fall back to a forced move if the target is briefly locked by
  # an in-flight scp read (the scp side also retries once).
  if (Test-Path -LiteralPath $path) {
    try { [System.IO.File]::Replace($tmp, $path, $null) }
    catch { Move-Item -LiteralPath $tmp -Destination $path -Force }
  } else {
    Move-Item -LiteralPath $tmp -Destination $path -Force
  }
}

if (-not $Loop) {
  Read-Config $ConfigFile
  Save-Frame $Out
  return
}

# --- loop / near-live streaming mode ---
if (Test-Path -LiteralPath $Stop) { Remove-Item -LiteralPath $Stop -Force -ErrorAction SilentlyContinue }
Log "loop start out=$Out fmt=$Format q=$Quality scale=$Scale interval=${IntervalMs}ms max=${MaxSeconds}s"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
  while ($true) {
    if (Test-Path -LiteralPath $Stop)              { Log "loop stop (sentinel)";       break }
    if ($sw.Elapsed.TotalSeconds -ge $MaxSeconds)  { Log "loop stop (max ${MaxSeconds}s)"; break }
    Read-Config $ConfigFile
    try { Save-Frame $Out }
    catch { Log "frame error: $($_.Exception.Message)"; Start-Sleep -Milliseconds 500 }
    Start-Sleep -Milliseconds $IntervalMs
  }
} finally {
  # Leave no stale frame behind: latest_frame() treats an absent live.* as
  # "stream not running" and falls back to a fresh one-shot.
  Remove-Item -LiteralPath $Out       -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath "$Out.tmp" -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $Stop      -Force -ErrorAction SilentlyContinue
  Log "loop exited"
}
