# After the daily forecast: put the PC back to sleep, but only if the scheduled task woke it
# and nobody has used it since. Called at the end of scripts\daily_forecast.cmd.
#
#   -TaskStart  when the daily run began (the cmd passes it in)
#   -IdleMinutes  minimum minutes with no mouse/keyboard input before we'll sleep (default 10)
#
# Rules (all must hold):
#   1. The PC woke from sleep shortly before the run started (within 15 minutes), i.e. we woke it.
#   2. No keyboard/mouse input for at least IdleMinutes -- if someone's using it, leave it alone.
# Sleep means regular sleep (S3), not hibernate or shutdown.
param([datetime]$TaskStart = (Get-Date), [int]$IdleMinutes = 10)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WsuIdle {
  [StructLayout(LayoutKind.Sequential)] struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
  [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO info);
  public static double Seconds() {
    var info = new LASTINPUTINFO(); info.cbSize = (uint)Marshal.SizeOf(info);
    GetLastInputInfo(ref info);
    return ((uint)Environment.TickCount - info.dwTime) / 1000.0;
  }
}
"@

$idleMin = [WsuIdle]::Seconds() / 60
# Most recent wake from sleep: Power-Troubleshooter event 1 in the System log.
$wake = Get-WinEvent -FilterHashtable @{LogName = 'System'; ProviderName = 'Microsoft-Windows-Power-Troubleshooter'; Id = 1} -MaxEvents 1 -ErrorAction SilentlyContinue
$wokeAt = if ($wake) { $wake.TimeCreated } else { $null }
$wokeForUs = $wokeAt -and ($wokeAt -le $TaskStart) -and (($TaskStart - $wokeAt).TotalMinutes -le 15)

"sleep check: task started $TaskStart; last wake $wokeAt; idle $([math]::Round($idleMin, 1)) min"
if ($wokeForUs -and $idleMin -ge $IdleMinutes) {
  "going back to sleep"
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend, $false, $false) | Out-Null
} else {
  "staying awake (" + $(if (-not $wokeForUs) { "the PC was already awake" } else { "someone is using it" }) + ")"
}
