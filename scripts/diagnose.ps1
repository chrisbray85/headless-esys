# diagnose.ps1 - one-shot health check for the ISTA-MCP capture/input path. Runs over
# plain SSH. Emits compact JSON so the Mac side can turn "no frame produced" into an
# actual cause. The decisive check is scheduler_ok: capture + input both ride Windows
# Task Scheduler, and a pending-reboot/limbo state can leave it accepting /run and
# reporting success while executing NOTHING (both session 0 and session 1). This
# script proves that with a throwaway SYSTEM marker task.
$ErrorActionPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch {}
$dir = "C:\ista-mcp"

# --- desktop session: is a user interactively logged on (needed for /it capture)? ---
$desktop = $false; $sessions = @()
foreach ($ln in (qwinsta 2>$null)) {
  if ($ln -match '^\s*>?\s*(\S+)\s+(\S.*?)\s+(\d+)\s+(Active|Disc)\b') {
    $u = $Matches[2].Trim()
    $sessions += ("{0}:{1}:{2}" -f $Matches[1], $u, $Matches[4])
    if ($u -and $u -notmatch '^\d+$' -and $Matches[4] -eq 'Active') { $desktop = $true }
  }
}

# --- Defender exclusion for our dir (missing => scripts silently quarantined) ---
$excluded = $false
try { $excluded = @((Get-MpPreference).ExclusionPath) -contains $dir } catch {}

# --- pending reboot (limbo state that wedges Task Scheduler) ---
$pfro = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager" -Name PendingFileRenameOperations -EA SilentlyContinue)
$pendCount = if ($pfro) { @($pfro.PendingFileRenameOperations).Count } else { 0 }
$cbs = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"
$wu  = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"
$pendingReboot = ($pendCount -gt 0) -or $cbs -or $wu

# --- scheduler actually executes? throwaway SYSTEM marker task (session 0) ---
$schedOk = $false
$mk = "$dir\diagmark.txt"
Remove-Item $mk -Force -EA SilentlyContinue
schtasks /create /tn IstaDiag /tr "cmd /c echo ok > $mk" /sc once /st 23:59 /ru SYSTEM /f 2>&1 | Out-Null
# Clear the default "don't start on batteries" condition or this probe (and every
# other task) sits in Queued whenever the laptop is unplugged at the car.
try { Set-ScheduledTask -TaskName IstaDiag -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries) -EA Stop | Out-Null } catch {}
schtasks /run /tn IstaDiag 2>&1 | Out-Null
foreach ($n in 1..14) { Start-Sleep -Milliseconds 500; if (Test-Path $mk) { $schedOk = $true; break } }
schtasks /delete /tn IstaDiag /f 2>&1 | Out-Null
Remove-Item $mk -Force -EA SilentlyContinue

# --- on battery? (BatteryStatus 1 = discharging) ---
$bat = Get-CimInstance Win32_Battery -EA SilentlyContinue | Select-Object -First 1
$onBattery = [bool]($bat -and $bat.BatteryStatus -eq 1)

# --- ISTA process + true integrity level ---
$proc = Get-Process ISTAGUI -EA SilentlyContinue | Select-Object -First 1
$istaRun = [bool]$proc
$integrity = "n/a"
if ($proc) {
  try {
    if (-not ("Tok" -as [type])) {
      Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public class Tok {
  [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr h,uint a,out IntPtr t);
  [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr t,int c,IntPtr b,int l,out int r);
  [DllImport("advapi32.dll",SetLastError=true)] static extern IntPtr GetSidSubAuthority(IntPtr s,uint i);
  public static int Level(IntPtr proc){ IntPtr tok; if(!OpenProcessToken(proc,0x0008,out tok)) return -1;
    int len; GetTokenInformation(tok,25,IntPtr.Zero,0,out len); IntPtr buf=Marshal.AllocHGlobal(len);
    try{ if(!GetTokenInformation(tok,25,buf,len,out len)) return -2; return Marshal.ReadInt32(GetSidSubAuthority(Marshal.ReadIntPtr(buf),0)); }
    finally{ Marshal.FreeHGlobal(buf); } } }
'@
    }
    $integrity = switch ([Tok]::Level($proc.Handle)) {
      0x3000 {"high"} 0x4000 {"system"} 0x2000 {"medium"} 0x1000 {"low"} default {"unknown"} }
  } catch { $integrity = "probe-failed" }
}

# --- doc html + live stream freshness ---
$docPath = Join-Path $env:LOCALAPPDATA "Temp\tempWebView.html"
$docItem = Get-Item -LiteralPath $docPath -EA SilentlyContinue
$docAge = if ($docItem) { [int64]((Get-Date).ToUniversalTime() - $docItem.LastWriteTimeUtc).TotalMilliseconds } else { $null }
$live = Get-Item -LiteralPath "$dir\live.jpg" -EA SilentlyContinue
$liveAge = if ($live) { [int64]((Get-Date).ToUniversalTime() - $live.LastWriteTimeUtc).TotalMilliseconds } else { $null }

[pscustomobject]@{
  desktop_session   = $desktop
  sessions          = $sessions
  defender_excluded = $excluded
  scheduler_ok      = $schedOk
  on_battery        = $onBattery
  pending_reboot    = $pendingReboot
  pending_files     = $pendCount
  ista_running      = $istaRun
  ista_integrity    = $integrity
  doc_age_ms        = $docAge
  live_stream_ms    = $liveAge
} | ConvertTo-Json -Compress
