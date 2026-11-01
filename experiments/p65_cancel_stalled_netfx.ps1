# Request normal Ctrl+C cancellation only on this task's isolated DISM console.
# Never terminate DISM, CBS, Windows Update, or other system processes.
$ErrorActionPreference = 'Stop'
$taskCancelDir = 'E:/FPGA_Tools/Downloads/NetFx3-System-20261025T121739Z'
$taskCancelReport = [ordered]@{status='checking_owned_Dism_console'; target_pid=14392; signal_sent=$false; forced_termination=$false}
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class P65ConsoleCancel {
 [DllImport("kernel32.dll", SetLastError=true)] public static extern bool FreeConsole();
 [DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint pid);
 [DllImport("kernel32.dll", SetLastError=true)] public static extern uint GetConsoleProcessList(uint[] list, uint count);
 [DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
 [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GenerateConsoleCtrlEvent(uint type, uint group);
}
'@
$taskAttached = $false
try {
    $taskDism = Get-CimInstance Win32_Process -Filter 'ProcessId=14392'
    if (!$taskDism) { throw 'Owned DISM already exited; do not signal' }
    if ($taskDism.Name -ine 'Dism.exe' -or $taskDism.CommandLine -notlike '*NetFx3*' -or
        $taskDism.CommandLine -notlike '*NetFx3-System-20261025T121739Z*' -or
        $taskDism.CreationDate.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss') -ne '2026-10-25T12:17:40') {
        throw 'Owned DISM identity mismatch'
    }
    $taskCancelReport.target_command = $taskDism.CommandLine
    [void][P65ConsoleCancel]::FreeConsole()
    if (![P65ConsoleCancel]::AttachConsole(14392)) { throw 'No accessible isolated console; no cancellation sent' }
    $taskAttached = $true
    $taskConsoleIds = [uint32[]]::new(32)
    $taskConsoleCount = [P65ConsoleCancel]::GetConsoleProcessList($taskConsoleIds,32)
    if ($taskConsoleCount -eq 0 -or $taskConsoleCount -gt 32) { throw 'Ambiguous console membership' }
    $taskConsoleIds = @($taskConsoleIds[0..($taskConsoleCount-1)])
    $taskCancelReport.console_process_ids = $taskConsoleIds
    if ($taskConsoleIds -notcontains 14392 -or $taskConsoleIds -notcontains $PID -or
        @($taskConsoleIds | Where-Object { $_ -ne 14392 -and $_ -ne $PID }).Count -ne 0) {
        throw 'Console contains unrelated processes; refusing Ctrl+C'
    }
    if (![P65ConsoleCancel]::SetConsoleCtrlHandler([IntPtr]::Zero,$true)) { throw 'Unable to protect helper' }
    if (![P65ConsoleCancel]::GenerateConsoleCtrlEvent(0,0)) { throw 'Cancellation request failed' }
    $taskCancelReport.signal_sent = $true
    $taskCancelReport.status = 'normal_CtrlC_requested_on_verified_isolated_DISM_console'
    Start-Sleep -Seconds 2
} catch {
    $taskCancelReport.status = 'normal_cancel_unconfirmed'
    $taskCancelReport.error = $_.Exception.Message
} finally {
    if ($taskAttached) { [void][P65ConsoleCancel]::FreeConsole() }
    $taskCancelReport.completed_local = (Get-Date -Format o)
    $taskCancelReport | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskCancelDir 'normal-cancel-report.json') -Encoding UTF8
}
