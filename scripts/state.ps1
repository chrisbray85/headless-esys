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
# Emit UTF-8 so non-ASCII in ISTA docs (deg/plus-minus/micro/pilcrow) survives the
# SSH pipe: without this, ConvertTo-Json's output is re-encoded to the console
# codepage (cp1252) and a lone high byte like 0xB6 breaks the Mac's UTF-8 decode.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch {}
$dir = "C:\ista-mcp"
$docPath = Join-Path $env:LOCALAPPDATA "Temp\tempWebView.html"

function AgeMs($item) {
  if (-not $item) { return $null }
  [int64]((Get-Date).ToUniversalTime() - $item.LastWriteTimeUtc).TotalMilliseconds
}

function Read-TextSmart($path) {
  # Read bytes with a shared handle (WebView2 may hold the file open) and decode
  # BOM > strict-UTF-8 > Windows-1252. PS 5.1's Get-Content -Raw defaults to ANSI,
  # which mangles ISTA's UTF-8 doc; this gets a correct .NET string every time.
  try {
    $fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open,
          [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try { $b = New-Object byte[] $fs.Length; [void]$fs.Read($b, 0, $b.Length) }
    finally { $fs.Close() }
  } catch { return $null }
  if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) {
    return [System.Text.Encoding]::UTF8.GetString($b, 3, $b.Length - 3)
  }
  try {
    return (New-Object System.Text.UTF8Encoding($false, $true)).GetString($b)
  } catch {
    return [System.Text.Encoding]::GetEncoding(1252).GetString($b)
  }
}

# --- doc html ---
$html = $null; $htmlMs = $null
$docItem = Get-Item -LiteralPath $docPath -ErrorAction SilentlyContinue
if ($docItem) {
  $htmlMs = AgeMs $docItem
  $html = Read-TextSmart $docPath
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
# Note: real elevation is reported by ista_elevation() (elev.ps1 reads the token
# integrity level). We deliberately DON'T probe it here on the hot path - the cheap
# handle trick is unreliable from an elevated SSH session (it always says "not
# elevated"). The RUNASADMIN layer flag below is the cheap, honest proxy: layer set
# + ISTA running => almost certainly elevated => injected input will be blocked.
$proc = Get-Process ISTAGUI -ErrorAction SilentlyContinue | Select-Object -First 1
$running = [bool]$proc
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
  runasadmin_layer = $layerOn
} | ConvertTo-Json -Compress
