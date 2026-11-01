[CmdletBinding()]
param(
    [string]$VivadoBat = 'E:\FPGA_Tools\Xilinx\Vivado\2021.1\bin\vivado.bat',
    [string]$HdlRoot = '',
    [ValidateRange(1, 4)][int]$OocJobs = 1
)

$ErrorActionPreference = 'Stop'
$prepared = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'short-workspace-manifest.json') -Raw | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($HdlRoot)) { $HdlRoot = $prepared.hdl_root }
$HdlRoot = [IO.Path]::GetFullPath($HdlRoot)
if ($HdlRoot.Length -gt 60) { throw 'Use a short HDL workspace path (at most 60 characters).' }
if (-not (Test-Path -LiteralPath $VivadoBat -PathType Leaf)) { throw "Vivado 2021.1 is not installed at $VivadoBat" }
if (-not (Test-Path -LiteralPath $HdlRoot -PathType Container)) { throw "Prepared HDL workspace is missing: $HdlRoot" }
foreach ($sourceRow in $prepared.files) {
    $sourcePath = [IO.Path]::GetFullPath((Join-Path $HdlRoot $sourceRow.hdl_relative_path.Replace('/', '\')))
    if (-not $sourcePath.StartsWith($HdlRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Source manifest path escaped the HDL root.' }
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw "Required source is missing: $sourcePath" }
    if ((Get-Item -LiteralPath $sourcePath).Length -ne $sourceRow.bytes) { throw "Prepared source size changed: $sourcePath" }
    if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceRow.sha256) { throw "Prepared source hash changed: $sourcePath" }
}
$workspaceFiles = @(Get-ChildItem -LiteralPath $HdlRoot -File -Recurse -Force)
if ($workspaceFiles.Count -ne $prepared.file_count) { throw 'Workspace contains additional files; prepare a new workspace before building.' }

$workRoot = [IO.Path]::GetDirectoryName($HdlRoot)
$runName = 'build-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
$logRoot = Join-Path $workRoot $runName
New-Item -ItemType Directory -Path $logRoot -ErrorAction Stop | Out-Null
$stageResults = [Collections.Generic.List[object]]::new()
$environmentNames = @('ADI_HDL_DIR', 'ADI_GHDL_DIR', 'REQUIRED_VIVADO_VERSION', 'ADI_IGNORE_VERSION_CHECK', 'ADI_USE_OOC_SYNTHESIS', 'ADI_USE_INCR_COMP', 'ADI_POWER_OPTIMIZATION', 'ADI_NO_BITSTREAM_COMPRESSION', 'ADI_GENERATE_UTILIZATION', 'ADI_GENERATE_XPA', 'ADI_MAX_OOC_JOBS')
$savedEnvironment = @{}
foreach ($environmentName in $environmentNames) {
    $environmentPath = 'Env:\' + $environmentName
    $exists = Test-Path -LiteralPath $environmentPath
    $savedEnvironment[$environmentName] = @{existed=$exists; value=[Environment]::GetEnvironmentVariable($environmentName, 'Process')}
    # .NET 10 preserves an empty variable when passed null. Vendor Tcl tests
    # existence, so remove via the environment provider instead of setting null.
    if ($exists) { Remove-Item -LiteralPath $environmentPath -ErrorAction Stop }
}
[Environment]::SetEnvironmentVariable('ADI_HDL_DIR', $HdlRoot.Replace('\', '/'), 'Process')
[Environment]::SetEnvironmentVariable('ADI_MAX_OOC_JOBS', [string]$OocJobs, 'Process')
[Environment]::SetEnvironmentVariable('REQUIRED_VIVADO_VERSION', '2021.1', 'Process')
$buildStarted = Get-Date
$complete = $false
$buildFailure = $null

function Invoke-VendorStage {
    param([string]$StageName, [string]$WorkingDirectory, [string]$SourceScript)
    $stageStarted = Get-Date
    $stageLog = Join-Path $logRoot ($StageName + '.log')
    $stageJournal = Join-Path $logRoot ($StageName + '.jou')
    $consoleLog = Join-Path $logRoot ($StageName + '-console.txt')
    $stageArguments = @('-mode', 'batch', '-source', $SourceScript, '-log', $stageLog, '-journal', $stageJournal)
    $stageExitCode = $null
    $stageFailure = $null
    $locationPushed = $false
    try {
        Push-Location -LiteralPath $WorkingDirectory
        $locationPushed = $true
        $nativePreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $global:LASTEXITCODE = $null
            & $VivadoBat @stageArguments 2>&1 | Tee-Object -FilePath $consoleLog -ErrorAction Stop
            $stageExitCode = $global:LASTEXITCODE
        }
        finally { $ErrorActionPreference = $nativePreference }
    }
    catch { $stageFailure = $_.Exception.Message; throw }
    finally {
        if ($locationPushed) { Pop-Location }
        $stageResults.Add([pscustomobject]@{stage=$StageName; source=$SourceScript; working_directory=$WorkingDirectory; started=$stageStarted.ToString('o'); ended=(Get-Date).ToString('o'); exit_code=$stageExitCode; launch_or_log_error=$stageFailure; log=$stageLog; journal=$stageJournal; console=$consoleLog})
    }
    if ($null -eq $stageExitCode -or $stageExitCode -ne 0) { throw "Vendor stage $StageName failed with exit code $stageExitCode; see $stageLog" }
}

try {
    Invoke-VendorStage -StageName '00-tool-preflight' -WorkingDirectory $workRoot -SourceScript (Join-Path $PSScriptRoot 'preflight-vivado.tcl')
    # This order mirrors the original Makefile's recursive Xilinx library dependencies.
    $libraries = @('axi_ad9361', 'util_cdc', 'util_axis_fifo', 'axi_dmac', 'util_pack/util_cpack2', 'util_pack/util_upack2')
    $stageNumber = 1
    foreach ($library in $libraries) {
        $libraryName = ($library -split '/')[-1]
        $libraryDirectory = Join-Path (Join-Path $HdlRoot 'library') $library.Replace('/', '\')
        Invoke-VendorStage -StageName ('{0:d2}-{1}' -f $stageNumber, $libraryName) -WorkingDirectory $libraryDirectory -SourceScript ($libraryName + '_ip.tcl')
        if (-not (Test-Path -LiteralPath (Join-Path $libraryDirectory 'component.xml') -PathType Leaf)) { throw "IP packaging did not produce component.xml: $library" }
        $stageNumber++
    }
    $projectDirectory = Join-Path $HdlRoot 'projects\pzp201'
    Invoke-VendorStage -StageName '07-pzp201-original-project' -WorkingDirectory $projectDirectory -SourceScript 'system_project.tcl'
    $xsa = Join-Path $projectDirectory 'pzp201.sdk\system_top.xsa'
    $bit = Join-Path $projectDirectory 'pzp201.runs\impl_1\system_top.bit'
    foreach ($outputPath in @($xsa, $bit)) {
        if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf) -or (Get-Item -LiteralPath $outputPath).Length -eq 0) { throw "Expected vendor build output is missing: $outputPath" }
    }
    $complete = $true
    Write-Output "P06 vendor build generated $xsa and $bit; board validation remains separate."
}
catch { $buildFailure = $_.Exception.Message; throw }
finally {
    try {
        $buildRecord = [pscustomobject]@{started=$buildStarted.ToString('o'); ended=(Get-Date).ToString('o'); hdl_root=$HdlRoot; vivado_launcher=$VivadoBat; required_vivado='2021.1'; required_part='xc7z020clg400-2'; pristine_sources_verified=$true; ooc_jobs=$OocJobs; successful=$complete; error=$buildFailure; board_accessed=$false; ip_upgrade_requested=$false; stages=@($stageResults.ToArray())}
        $buildRecord | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $logRoot 'build-record.json') -Encoding UTF8 -ErrorAction Stop
    }
    catch {
        if ($null -ne $buildFailure) { Write-Warning "Could not write build-record.json: $($_.Exception.Message). The initial build failure remains the reported error." }
        else { throw }
    }
    finally {
        foreach ($environmentName in $environmentNames) {
            $previous = $savedEnvironment[$environmentName]
            $environmentPath = 'Env:\' + $environmentName
            if ($previous.existed) { [Environment]::SetEnvironmentVariable($environmentName, $previous.value, 'Process') }
            elseif (Test-Path -LiteralPath $environmentPath) { Remove-Item -LiteralPath $environmentPath -ErrorAction Stop }
        }
    }
}
