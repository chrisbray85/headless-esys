# state.ps1 - ONE-round-trip state bundle for ISTA-MCP. Runs over plain SSH (it only
# reads files and triggers the IstaGrab scheduled task - no desktop access needed).
#
# Emits a single compressed JSON object on stdout:
#   html            - raw text of ISTA's tempWebView.html (the currently displayed
#                     procedure / fault / functional-description content), or null
#   html_ms         - age of that file in ms (how current the doc text is)
#   frame_b64       - base64 JPEG of the screen, or null if -NoFrame / no frame
#   frame_ms        - age of the frame in ms
#   frame_src       - "live" (stream loop), "oneshot" (fresh IstaGrab), "stale", "none"
#   ista_running    - ISTAGUI.exe process present
#   ista_elevated   - true/false/null; heuristic: opening a full-access handle to an
#                     elevated process from this non-elevated SSH shell throws
#   runasadmin_layer- HKCU AppCompatFlags RUNASADMIN flag set for ISTAGUI.exe
#                     (true => next ISTA launch is elevated => UIPI blocks our input)
param(
  [int]$FreshMs = 2500,   # live.jpg younger than this is served as-is, no trigger
  [switch]$NoFrame,       # text-only (read_doc path) - skips capture entirely
  [int]$WaitS   = 8       # max seconds to wait for a fresh one-shot frame
)
$ErrorActionPreference = "SilentlyContinue"
$dir = "C:\ista-mcp"
$docPath = Join-Path $env:LOCALAPPDATA "Temp\tempWebView.html"

function AgeMs($item) {
  if (-not $item) { return $null }
  [int64]((Get-Date).ToUniversalTime() - $item.LastWriteTimeUtc).TotalMilliseconds
}

# --- doc html ---
$html = $null; $htmlMs = $null
$docItem = Get-Item -LiteralPath $docPath -ErrorAction SilentlyContinue
if ($docItem) {
  $htmlMs = AgeMs $docItem
  $html = Get-Content -LiteralPath $docPath -Raw -ErrorAction SilentlyContinue
  if ($html -and $html.Length -gt 600000) { $html = $html.Substring(0, 600000) + "`n[TRUNCATED at 600000 chars]" }
}

# --- frame ---
$b64 = $null; $frameMs = $null; $src = "none"
if (-not $NoFrame) {
  $pick = $null
  $live = Get-Item -LiteralPath "$dir\live.jpg" -ErrorAction SilentlyContinue
  if ($live -and (AgeMs $live) -lt $FreshMs) {
    $pick = $live; $src = "live"
  } else {
    $shotPath = "$dir\screen.jpg"
    $beforeItem = Get-Item -LiteralPath $shotPath -ErrorAction SilentlyContinue
    $before = if ($beforeItem) { $beforeItem.LastWriteTimeUtc.Ticks } else { 0 }
    schtasks /run /tn IstaGrab 2>&1 | Out-Null
    $deadline = (Get-Date).AddSeconds($WaitS)
    while ((Get-Date) -lt $deadline) {
      Start-Sleep -Milliseconds 250
      $cur = Get-Item -LiteralPath $shotPath -ErrorAction SilentlyContinue
      if ($cur -and $cur.LastWriteTimeUtc.Ticks -gt $before) { $pick = $cur; $src = "oneshot"; break }
    }
    if (-not $pick -and $beforeItem) { $pick = $beforeItem; $src = "stale" }
  }
  if ($pick) {
    $bytes = $null
    foreach ($try in 1..2) {  # grab.ps1 publishes atomically; retry covers a rare in-flight Replace()
      try { $bytes = [System.IO.File]::ReadAllBytes($pick.FullName); break }
      catch { Start-Sleep -Milliseconds 150 }
    }
    if ($bytes) {
      $b64 = [Convert]::ToBase64String($bytes)
      $frameMs = AgeMs (Get-Item -LiteralPath $pick.FullName -ErrorAction SilentlyContinue)
    } else { $src = "none" }
  }
}

# --- ISTA process + elevation ---
$proc = Get-Process ISTAGUI -ErrorAction SilentlyContinue | Select-Object -First 1
$running = [bool]$proc
$elevated = $null
if ($proc) {
  try { $null = $proc.Handle; $elevated = $false } catch { $elevated = $true }
}
$layerOn = $false
$layers = Get-ItemProperty "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" -ErrorAction SilentlyContinue
if ($layers) {
  foreach ($p in $layers.PSObject.Properties) {
    if ($p.Name -like "*ISTAGUI*" -and "$($p.Value)" -match "RUNASADMIN") { $layerOn = $true }
  }
}

[pscustomobject]@{
  html             = $html
  html_ms          = $htmlMs
  frame_b64        = $b64
  frame_ms         = $frameMs
  frame_src        = $src
  ista_running     = $running
  ista_elevated    = $elevated
  runasadmin_layer = $layerOn
} | ConvertTo-Json -Compress
