param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$taskNetFxSource = 'E:/FPGA_Tools/Downloads/NetFx3-System-20261025T121739Z/source'
$taskNetFxFile = Join-Path $taskNetFxSource 'Microsoft-Windows-NetFx3-OnDemand-Package~31bf3856ad364e35~amd64~~.cab'
$taskNetFxReport = [ordered]@{status='checking_offline_NetFx3_source'; started_local=(Get-Date -Format o); automatic_reboot=$false; source=$taskNetFxFile; board_operations=$false}
function Save-TaskReport {
    $taskNetFxReport | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'report.json') -Encoding UTF8
}
try {
    if (Get-Process -Name dism -ErrorAction SilentlyContinue) { throw 'Another DISM session exists; no concurrent installation' }
    $taskNetFxHash = (Get-FileHash -LiteralPath $taskNetFxFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($taskNetFxHash -ne 'dc3af93af5c64dc115409437d31018baf2c3c46167806a599124bc905ae512f6') { throw 'Offline source SHA mismatch' }
    $taskNetFxReport.sha256 = $taskNetFxHash
    $taskNetFxReport.before = Get-WindowsOptionalFeature -Online -FeatureName NetFx3 | Select-Object FeatureName,State,RestartRequired
    $taskNetFxReport.status = 'offline_NetFx3_enable_running'
    Save-TaskReport
    & "$env:WINDIR/System32/dism.exe" /Online /Enable-Feature /FeatureName:NetFx3 /All /LimitAccess "/Source:$taskNetFxSource" /NoRestart "/LogPath:$OutputDirectory/dism.log" *> (Join-Path $OutputDirectory 'console.log')
    $taskNetFxReport.exit_code = $LASTEXITCODE
    $taskNetFxReport.after = Get-WindowsOptionalFeature -Online -FeatureName NetFx3 | Select-Object FeatureName,State,RestartRequired
    if (($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 3010) -and $taskNetFxReport.after.State.ToString() -eq 'Enabled') {
        $taskNetFxReport.status = 'NetFx3_enabled_editor_launch_not_yet_verified'
    } elseif ($taskNetFxReport.exit_code -eq 3010 -or $taskNetFxReport.after.State.ToString() -eq 'EnablePending') {
        $taskNetFxReport.status = 'NetFx3_enable_requires_reboot_not_rebooted'
    } else {
        $taskNetFxReport.status = 'offline_NetFx3_enable_failed'
    }
    $taskNetFxReport.CLR2_DLL_present = Test-Path -LiteralPath "$env:WINDIR/Microsoft.NET/Framework/v2.0.50727/mscorwks.dll"
} catch {
    $taskNetFxReport.status = 'offline_NetFx3_enable_error'
    $taskNetFxReport.error = $_.Exception.Message
} finally {
    $taskNetFxReport.completed_local = (Get-Date -Format o)
    Save-TaskReport
}
