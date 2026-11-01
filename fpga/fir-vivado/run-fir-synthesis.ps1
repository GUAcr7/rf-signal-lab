[CmdletBinding()]
param(
    [string]$VivadoBat = 'E:\FPGA_Tools\Xilinx\Vivado\2021.1\bin\vivado.bat',
    [string]$WorkParent = 'E:\FPGA_Tools\Work',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$contractPath = Join-Path $PSScriptRoot 'expected-contract.json'
$contract = Get-Content -LiteralPath $contractPath -Raw | ConvertFrom-Json
if ($contract.required_vivado -ne '2021.1' -or $contract.part -ne 'xc7z020clg400-2' -or $contract.top -ne 'fixed_fir_iq' -or $contract.taps -ne 63 -or $contract.clock_period_ns -ne 10) { throw 'Unexpected FIR contract.' }
$sources = @()
foreach ($row in $contract.sources) {
    $path = Join-Path $projectRoot $row.relative_path.Replace('/', '\')
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required source is missing: $path" }
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $row.sha256) { throw "Source changed since the qualified simulation: $path" }
    $sources += [pscustomobject]@{relative_path=$row.relative_path; original_path=$path; bytes=(Get-Item -LiteralPath $path).Length; sha256=$hash; synthesis_input=$row.synthesis_input}
}
$coefficientPath = Join-Path $projectRoot 'fpga\ip\fir63_q17.hex'
$words = [IO.File]::ReadAllLines($coefficientPath)
if ($words.Count -ne 63 -or @($words | Where-Object {$_ -notmatch '\A[0-3][0-9a-fA-F]{4}\z'}).Count -ne 0) { throw 'Coefficient input must contain exactly 63 plain 18-bit hexadecimal words.' }
$evidence = @()
foreach ($relative in @($contract.simulation_report, $contract.default_coeff_report)) {
    $path = Join-Path $projectRoot $relative.Replace('/', '\')
    $report = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if (-not $report.all_passed) { throw "Simulation evidence was not successful: $path" }
    foreach ($row in $sources) {
        $sourceMatches = @($report.sources | Where-Object {[IO.Path]::GetFileName($_.path) -eq [IO.Path]::GetFileName($row.original_path) -and $_.sha256 -eq $row.sha256})
        if ($sourceMatches.Count -ne 1) { throw "Simulation source fingerprint does not match: $($row.relative_path)" }
    }
    if ($relative -eq $contract.simulation_report -and ($report.case_count -ne 18 -or $report.sample_comparisons -ne 72356)) { throw 'Unexpected full simulation coverage.' }
    if ($relative -eq $contract.default_coeff_report -and (-not $report.default_coefficient_initialization -or $report.random_stalls_enabled -or $report.sample_comparisons -ne 1086)) { throw 'Unexpected default-coefficient qualification.' }
    $evidence += [pscustomobject]@{path=$path; sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant(); comparisons=$report.sample_comparisons; all_passed=$true}
}
if ($CheckOnly) {
    [pscustomobject]@{source_validation_passed=$true; synthesis_started=$false; expected_version='2021.1'; part='xc7z020clg400-2'; clock_period_ns=10; coefficient_words=$words.Count; sources=$sources; simulation_evidence=$evidence}
    return
}
if (-not [IO.Path]::IsPathRooted($VivadoBat) -or -not (Test-Path -LiteralPath $VivadoBat -PathType Leaf)) { throw 'An installed absolute Vivado 2021.1 batch launcher is required.' }
if ($WorkParent -notmatch '\A[A-Za-z]:[\\/]') { throw 'Use an absolute local Windows work directory.' }
$WorkParent = [IO.Path]::GetFullPath($WorkParent).TrimEnd('\')
if ($WorkParent.Length -gt 40) { throw 'Use a short work parent (at most 40 characters).' }
$runName = 'p07-fir-ooc-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
$runRoot = Join-Path $WorkParent $runName
if (Test-Path -LiteralPath $runRoot) { throw "Refusing to overwrite an existing run: $runRoot" }
New-Item -ItemType Directory -Path $runRoot -ErrorAction Stop | Out-Null
$started = Get-Date
$exitCode = $null
$failure = $null
$complete = $false
$toolStarted = $false
$locationPushed = $false
$savedEnvironment = @{}
$metrics = @{}
$resources = @{}
$artifacts = @()
$environmentNames = @('ADI_HDL_DIR','ADI_GHDL_DIR','REQUIRED_VIVADO_VERSION','ADI_IGNORE_VERSION_CHECK','ADI_USE_OOC_SYNTHESIS','ADI_USE_INCR_COMP','ADI_POWER_OPTIMIZATION','ADI_NO_BITSTREAM_COMPRESSION','ADI_GENERATE_UTILIZATION','ADI_GENERATE_XPA','ADI_MAX_OOC_JOBS','ADI_VIVADO_IP_LIBRARY','ADI_DISABLE_MESSAGE_SUPPRESION')
try {
    foreach ($row in $sources | Where-Object {$_.synthesis_input}) {
        $destination = Join-Path $runRoot $row.relative_path.Replace('/', '\')
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($destination)) -Force | Out-Null
        Copy-Item -LiteralPath $row.original_path -Destination $destination -ErrorAction Stop
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $row.sha256) { throw "Copy fingerprint failed: $destination" }
    }
    foreach ($name in @('synth_fir.tcl','fir_internal_100mhz.xdc','expected-contract.json')) {
        $source = Join-Path $PSScriptRoot $name
        $destination = Join-Path $runRoot $name
        Copy-Item -LiteralPath $source -Destination $destination -ErrorAction Stop
        if ((Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $destination).Hash) { throw "Preparation script copy changed: $name" }
    }
    $prepared = [pscustomobject]@{prepared_at=(Get-Date).ToString('o'); run_root=$runRoot; sources=$sources; simulation_evidence=$evidence; preparation_scripts=@(Get-ChildItem -LiteralPath $PSScriptRoot -File | Where-Object {$_.Extension -in @('.ps1','.tcl','.xdc','.json')} | ForEach-Object {[pscustomobject]@{path=$_.FullName; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})}
    $prepared | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runRoot 'source-manifest.json') -Encoding UTF8
    foreach ($name in $environmentNames) {
        $environmentPath = 'Env:\' + $name
        $exists = Test-Path -LiteralPath $environmentPath
        $savedEnvironment[$name] = @{existed=$exists; value=[Environment]::GetEnvironmentVariable($name,'Process')}
        if ($exists) { Remove-Item -LiteralPath $environmentPath -ErrorAction Stop }
    }
    [Environment]::SetEnvironmentVariable('REQUIRED_VIVADO_VERSION','2021.1','Process')
    Push-Location -LiteralPath $runRoot
    $locationPushed = $true
    $nativePreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $global:LASTEXITCODE = $null
        $toolStarted = $true
        & $VivadoBat '-mode' 'batch' '-source' 'synth_fir.tcl' '-log' 'vivado.log' '-journal' 'vivado.jou' 2>&1 | Tee-Object -FilePath (Join-Path $runRoot 'console.txt') -ErrorAction Stop
        $exitCode = $global:LASTEXITCODE
    }
    finally { $ErrorActionPreference = $nativePreference }
    if ($null -eq $exitCode -or $exitCode -ne 0) { throw "FIR synthesis exited with code $exitCode; inspect $runRoot" }
    foreach ($name in @('utilization.rpt','utilization_hierarchical.rpt','timing_summary.rpt','internal_setup.rpt','internal_hold.rpt','check_timing.rpt','clocks.rpt','unconstrained_io.rpt','synth.dcp','internal_metrics.tsv')) {
        $path = Join-Path (Join-Path $runRoot 'reports') $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) { throw "Expected nonempty report/checkpoint missing: $name" }
        $artifacts += [pscustomobject]@{path=$path; bytes=(Get-Item -LiteralPath $path).Length; sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    foreach ($line in Get-Content -LiteralPath (Join-Path $runRoot 'reports\internal_metrics.tsv')) {
        $fields = $line -split "`t", 2
        if ($fields.Count -ne 2 -or $metrics.ContainsKey($fields[0])) { throw 'Malformed internal timing metrics.' }
        $metrics[$fields[0]] = $fields[1]
    }
    foreach ($line in Get-Content -LiteralPath (Join-Path $runRoot 'reports\utilization.rpt')) {
        if ($line -match '^\s*\|\s*(Slice LUTs\*?|Slice Registers\*?|Block RAM Tile\*?|DSPs\*?)\s*\|\s*([^|]+)\|') { $resources[$matches[1].TrimEnd('*')] = $matches[2].Trim() }
    }
    if ($resources.Count -ne 4) { throw 'Could not identify all four resource rows; inspect the official utilization report.' }
    if ([double]::Parse($resources['Slice LUTs'],[Globalization.CultureInfo]::InvariantCulture) -le 0 -or [double]::Parse($resources['Slice Registers'],[Globalization.CultureInfo]::InvariantCulture) -le 0) { throw 'FIR LUT/FF utilization is zero; inspect synthesis rather than accepting an empty design.' }
    $complete = $true
    Write-Output "FIR synthesis reports saved to $runRoot. Slack is a synthesis estimate; placement, routing and board performance remain unverified."
}
catch { $failure = $_.Exception.Message; throw }
finally {
    if ($locationPushed) { Pop-Location }
    try {
        $record = [pscustomobject]@{started=$started.ToString('o'); ended=(Get-Date).ToString('o'); run_root=$runRoot; vivado_launcher=$VivadoBat; expected_version='2021.1'; part='xc7z020clg400-2'; top='fixed_fir_iq'; taps=63; clock_period_ns=10; synthesis_started=$toolStarted; exit_code=$exitCode; reports_completed=$complete; error=$failure; sources=$sources; simulation_evidence=$evidence; artifacts=$artifacts; resource_report_used_rows=$resources; internal_synthesis_estimates=$metrics; placed=$false; routed=$false; timing_closed=$false; bitstream_written=$false; board_accessed=$false; io_delays_modeled=$false; sample_rate_measured=$false}
        $record | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath (Join-Path $runRoot 'run-record.json') -Encoding UTF8 -ErrorAction Stop
    }
    catch { if ($null -ne $failure) { Write-Warning "Could not write run-record.json: $($_.Exception.Message); retaining the original failure." } else { throw } }
    finally {
        foreach ($name in $savedEnvironment.Keys) {
            $previous = $savedEnvironment[$name]
            $environmentPath = 'Env:\' + $name
            if ($previous.existed) { [Environment]::SetEnvironmentVariable($name,$previous.value,'Process') }
            elseif (Test-Path -LiteralPath $environmentPath) { Remove-Item -LiteralPath $environmentPath -ErrorAction Stop }
        }
    }
}
