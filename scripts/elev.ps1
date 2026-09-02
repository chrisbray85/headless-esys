# elev.ps1 - manage the RUNASADMIN compatibility layer on ISTAGUI.exe. Runs over
# plain SSH (HKCU only, no admin token needed).
#
# WHY: ISTA set to always-run-as-admin means Windows UIPI silently discards every
# injected click/keystroke from our medium-integrity input task. Screenshots still
# work, so it *looks* like the click landed. For DIAGNOSIS run ISTA non-elevated
# (input works); flip it back on for PROGRAMMING/CODING sessions that need admin.
#
#   -Mode status : show the layer flag + whether ISTA is currently running elevated
#   -Mode off    : strip RUNASADMIN from the ISTAGUI layer value (keeps other flags)
#   -Mode on     : re-add RUNASADMIN (finds ISTAGUI.exe if no layer entry exists)
#
# A mode change only affects the NEXT ISTA launch - restart ISTA to apply.
param([ValidateSet("status","off","on")][string]$Mode = "status")
$ErrorActionPreference = "SilentlyContinue"
$key = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"

function IstaEntries {
  $l = Get-ItemProperty $key -ErrorAction SilentlyContinue
  if (-not $l) { return @() }
  @($l.PSObject.Properties | Where-Object { $_.Name -like "*ISTAGUI*" })
}

function ProcState {
  # Authoritative: read ISTA's token integrity level. The old "can I open the
  # handle" trick is useless here because OpenSSH gives an admin user a HIGH-
  # integrity session, so it can open any handle and every process looked
  # "non-elevated". Query the actual TokenIntegrityLevel instead.
  $p = Get-Process ISTAGUI -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $p) { return "ISTA process: not running" }
  try {
    if (-not ("Tok" -as [type])) {
      Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class Tok {
  [DllImport("advapi32.dll", SetLastError=true)] static extern bool OpenProcessToken(IntPtr h, uint a, out IntPtr t);
  [DllImport("advapi32.dll", SetLastError=true)] static extern bool GetTokenInformation(IntPtr t, int c, IntPtr b, int l, out int r);
  [DllImport("advapi32.dll", SetLastError=true)] static extern IntPtr GetSidSubAuthority(IntPtr s, uint i);
  public static int Level(IntPtr proc) {
    IntPtr tok; if(!OpenProcessToken(proc,0x0008,out tok)) return -1;
    int len; GetTokenInformation(tok,25,IntPtr.Zero,0,out len);
    IntPtr buf=Marshal.AllocHGlobal(len);
    try { if(!GetTokenInformation(tok,25,buf,len,out len)) return -2;
          return Marshal.ReadInt32(GetSidSubAuthority(Marshal.ReadIntPtr(buf),0)); }
    finally { Marshal.FreeHGlobal(buf); }
  }
}
'@
    }
    switch ([Tok]::Level($p.Handle)) {
      0x3000 { "ISTA process: running ELEVATED (high integrity - UIPI blocks input; run 'off' then restart ISTA)" }
      0x4000 { "ISTA process: running as SYSTEM (input blocked)" }
      0x2000 { "ISTA process: running non-elevated (medium integrity - input will land)" }
      0x1000 { "ISTA process: running low integrity" }
      default { "ISTA process: running, integrity unknown" }
    }
  } catch { "ISTA process: running, integrity probe failed ($($_.Exception.Message))" }
}

switch ($Mode) {
  "status" {
    $e = IstaEntries
    if (-not $e) { "layer: no ISTAGUI entry (next launch non-elevated)" }
    foreach ($p in $e) { "layer: $($p.Name) = $($p.Value)" }
    ProcState
  }
  "off" {
    $changed = $false
    foreach ($p in IstaEntries) {
      if ("$($p.Value)" -notmatch "RUNASADMIN") { continue }
      $rest = ("$($p.Value)" -replace "RUNASADMIN", "" -replace "\s+", " ").Trim()
      if ($rest -eq "~" -or $rest -eq "") {
        Remove-ItemProperty -Path $key -Name $p.Name -Force
        "removed layer entry: $($p.Name)"
      } else {
        Set-ItemProperty -Path $key -Name $p.Name -Value $rest -Force
        "stripped RUNASADMIN: $($p.Name) = $rest"
      }
      $changed = $true
    }
    if (-not $changed) { "nothing to do: no RUNASADMIN flag on ISTAGUI" }
    else { "RESTART ISTA to apply (close ISTAGUI, relaunch normally - NOT 'run as administrator')" }
    ProcState
  }
  "on" {
    $e = IstaEntries | Select-Object -First 1
    $path = $null
    if ($e) { $path = $e.Name }
    if (-not $path) {
      $p = Get-Process ISTAGUI -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($p -and $p.Path) { $path = $p.Path }
    }
    if (-not $path) {
      $hit = Get-ChildItem "C:\BMW" -Recurse -Filter "ISTAGUI.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($hit) { $path = $hit.FullName }
    }
    if (-not $path) { "FAILED: cannot locate ISTAGUI.exe (no layer entry, not running, not under C:\BMW)"; break }
    $val = if ($e -and "$($e.Value)" -match "\S") { ("$($e.Value)" -replace "RUNASADMIN","").Trim() + " RUNASADMIN" } else { "~ RUNASADMIN" }
    $val = ($val -replace "\s+", " ").Trim()
    if ($val -notmatch "^~") { $val = "~ $val" }
    Set-ItemProperty -Path $key -Name $path -Value $val -Force
    "set layer: $path = $val"
    "RESTART ISTA to apply (next launch runs elevated - for programming/coding)"
  }
}
