param(
    [string]$Port = 'COM5',
    [Parameter(Mandatory)][string]$EvidenceDirectory,
    [Parameter(Mandatory)][string]$LoginPassword,
    [ValidateSet('Run','Inspect','Retrieve','Commands')][string]$Mode = 'Run',
    [string[]]$Commands,
    [string]$BoardDirectory = '/tmp/arm-fir-check-20261011',
    [ValidateRange(1,180)][int]$CommandSeconds = 30
)
$ErrorActionPreference = 'Stop'
$serial = [System.IO.Ports.SerialPort]::new($Port,115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$serial.Handshake = [System.IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 1000
$serial.WriteTimeout = 3000
$transcript = [System.Text.StringBuilder]::new()
$stages = [System.Collections.Generic.List[object]]::new()
$report = [ordered]@{ started_at=(Get-Date).ToString('o'); port=$Port; status='running'; stages=$stages; rf_operations=$false; firmware_changes=$false }
function Wait-Serial([string]$Pattern,[int]$Seconds=20) {
    $buffer = [System.Text.StringBuilder]::new()
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) { [void]$buffer.Append($chunk); [void]$transcript.Append($chunk) }
        if ($buffer.Length -gt 33554432) { throw 'Serial response exceeded 32 MiB safety limit.' }
        if ($buffer.ToString() -match $Pattern) { return $buffer.ToString() }
        Start-Sleep -Milliseconds 50
    }
    throw "Serial response timed out waiting for $Pattern"
}
function Invoke-Board([string]$Name,[string]$Command,[int]$Seconds=30) {
    $marker = '__HOST_' + [guid]::NewGuid().ToString('N') + '__'
    $wire = $Command + '; printf ''\n' + $marker + ':%s\n'' "$?"'
    [void]$transcript.AppendLine("`n[STAGE $Name]")
    $serial.Write($wire + "`r")
    $output = Wait-Serial ('(?m)^' + $marker + ':(\d+)\r?$') $Seconds
    $match = [regex]::Match($output,('(?m)^' + $marker + ':(\d+)\r?$'))
    $code = [int]$match.Groups[1].Value
    $stages.Add([ordered]@{ name=$Name; command=$Command; exit_code=$code; output=$output })
    Write-Host "STAGE $Name exit=$code"
    if ($code -ne 0) { throw "Board stage $Name failed with exit $code" }
    return $output
}
if (Test-Path -LiteralPath $EvidenceDirectory) { throw 'Evidence directory already exists; refusing overwrite.' }
New-Item -ItemType Directory -Path $EvidenceDirectory | Out-Null
try {
    $serial.Open()
    $serial.Write("`r")
    $initial = Wait-Serial '(?m)(login:\s*$|#\s*$)' 10
    if ($initial -match 'login:\s*$') {
        $serial.Write("root`r")
        $null = Wait-Serial '(?i)password:\s*$' 10
        $serial.Write($LoginPassword + "`r")
        $authenticated = Wait-Serial '(?m)(#\s*$|login:\s*$)' 15
        if ($authenticated -notmatch '(?m)#\s*$') { throw 'Documented vendor login was rejected; no retry.' }
    }
    $identity = Invoke-Board 'identity' 'uname -a'
    if ($identity -notmatch 'Linux pzp201 .*armv7l') { throw 'Unexpected board identity; stopping before extraction.' }
    if ($Mode -in @('Inspect','Commands')) {
        $index = 0
        foreach ($command in $Commands) {
            $index++
            $output = Invoke-Board ("command-$index") $command $CommandSeconds
            Write-Output $output
        }
        $report.status = if ($Mode -eq 'Inspect') { 'inspection_completed' } else { 'command_sequence_completed' }
        $global:LASTEXITCODE = 0
        return
    }
    if ($Mode -eq 'Retrieve') {
        if ($BoardDirectory -notmatch '^/tmp/[A-Za-z0-9-]+$') { throw 'Result source must be one explicit temporary bundle directory.' }
        $stem = 'arm-fir-results-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
        $boardTar = '/tmp/' + $stem + '.tar'
        $boardGzip = $boardTar + '.gz'
        $null = Invoke-Board 'package-results' ("test ! -e $boardTar && tar -cf $boardTar -C $BoardDirectory outputs")
        $null = Invoke-Board 'compress-results' ("test ! -e $boardGzip && gzip -c $boardTar > $boardGzip")
        $hashOutput = Invoke-Board 'result-checksum' ("sha256sum $boardGzip")
        $hashMatch = [regex]::Match($hashOutput,('(?m)^([0-9a-f]{64})\s+' + [regex]::Escape($boardGzip) + '\r?$'))
        if (-not $hashMatch.Success) { throw 'Missing result archive checksum.' }
        $sizeOutput = Invoke-Board 'result-size' ("wc -c < $boardGzip")
        $sizeMatch = [regex]::Match($sizeOutput,'(?m)^\s*(\d+)\s*\r?$')
        if (-not $sizeMatch.Success) { throw 'Missing result archive byte count.' }
        $size = [long]$sizeMatch.Groups[1].Value
        if ($size -lt 1 -or $size -gt 10485760) { throw 'Unexpected result archive size.' }
        $encoded = Invoke-Board 'result-readback' ("od -An -v -tx1 $boardGzip") 180
        $hexLines = [regex]::Matches($encoded,'(?m)^[ \t]*(?:[0-9a-f]{2}[ \t]+)*[0-9a-f]{2}[ \t]*\r?$')
        $hex = [System.Text.StringBuilder]::new()
        foreach ($line in $hexLines) { [void]$hex.Append(($line.Value -replace '\s','')) }
        $bytes = [Convert]::FromHexString($hex.ToString())
        if ($bytes.Length -ne $size) { throw "Readback size mismatch: $($bytes.Length) vs $size" }
        $actualHash = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
        if ($actualHash -ne $hashMatch.Groups[1].Value) { throw 'Readback SHA256 mismatch.' }
        $hostArchive = Join-Path $EvidenceDirectory 'board-results.tar.gz'
        $file = [System.IO.File]::Open($hostArchive,[System.IO.FileMode]::CreateNew)
        try { $file.Write($bytes,0,$bytes.Length) } finally { $file.Dispose() }
        $report.status = 'results_retrieved_checksum_passed_content_verification_pending'
        $report.archive_bytes = $size
        $report.archive_sha256 = $actualHash
        $report.board_archive = $boardGzip
        Write-Output "RESULTS_RETRIEVED bytes=$size sha256=$actualHash"
        $global:LASTEXITCODE = 0
        return
    }
    $hash = Invoke-Board 'archive-checksum' 'sha256sum /tmp/arm-fir-check-20261011-1302.tar.gz'
    if ($hash -notmatch '(?m)^ddda514d8077987f1b02d3267bbe6c576054ee60a19beae416a6e4181fd10ae6\s+/tmp/arm-fir-check-20261011-1302.tar.gz\r?$') { throw 'Unexpected archive SHA256.' }
    $null = Invoke-Board 'decompress' 'cd /tmp && test ! -e arm-fir-check-20261011 && test ! -e arm-fir-check-20261011-1302.tar && gunzip -c arm-fir-check-20261011-1302.tar.gz > arm-fir-check-20261011-1302.tar'
    $tarHash = Invoke-Board 'tar-checksum' 'sha256sum /tmp/arm-fir-check-20261011-1302.tar'
    if ($tarHash -notmatch '(?m)^508f987544fecd948cd6a6c0d400455e5c2c7eb4fd0eceb2c02b464977bcace5\s+/tmp/arm-fir-check-20261011-1302.tar\r?$') { throw 'Unexpected decompressed tar SHA256.' }
    $null = Invoke-Board 'extract' 'cd /tmp && test ! -e arm-fir-check-20261011 && tar -xf arm-fir-check-20261011-1302.tar'
    $null = Invoke-Board 'inner-checksums' 'cd /tmp/arm-fir-check-20261011 && sha256sum -c SHA256SUMS'
    $run = Invoke-Board 'arm-tests' 'cd /tmp/arm-fir-check-20261011 && sh ./run-on-board.sh' 180
    if ($run -notmatch '(?m)^ARM_FIR_ALL_PASS cases=18 outputs=144712\r?$') { throw 'Final ARM pass marker missing.' }
    $passCases = [regex]::Matches($run,'(?m)^ARM_CASE_PASS [^\r\n]+').Count
    if ($passCases -ne 18) { throw "Expected 18 case passes; observed $passCases" }
    $report.status = 'board_execution_passed_outputs_retrieval_pending'
    $report.case_passes = $passCases
    $report.complex_outputs = 144712
    $report.authentication = 'documented_vendor_account_via_serial_not_GUI'
    Write-Output 'ARM_FIR_ALL_PASS cases=18 outputs=144712'
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
    Write-Output ('FAILED: ' + $_.Exception.Message)
} finally {
    $report.finished_at = (Get-Date).ToString('o')
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()

    # rf_operations used to be hardcoded $false, which mislabelled every
    # transmitting run as "no RF operations" - the transcript is the only
    # trustworthy source, and it records CYCLIC_PUSH_SUBMITTED only when the
    # program actually pushed samples into the DAC buffer.
    $transcriptText = $transcript.ToString()
    $pushed = $transcriptText -match 'CYCLIC_PUSH_SUBMITTED'
    $deadlineEnded = $transcriptText -match 'TX_SOFTWARE_DEADLINE_END'
    $wroteRf = $transcriptText -match 'rf_settings_written=true'
    $report.rf_operations = [bool]$pushed
    $report.rf_operations_basis = 'transcript contains CYCLIC_PUSH_SUBMITTED (samples reached the TX DMA buffer)'
    $report.rf_transmitted = [bool]($pushed -and $deadlineEnded)
    $report.rf_settings_written_by_host = [bool]$wroteRf
    if (-not $pushed -and -not $wroteRf) {
        $report.rf_operations_basis = 'transcript contains no CYCLIC_PUSH_SUBMITTED and no rf_settings_written=true (read-only run)'
    }

    $transcriptText | Set-Content -LiteralPath (Join-Path $EvidenceDirectory 'serial-transcript.txt') -Encoding utf8
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $EvidenceDirectory 'report.json') -Encoding utf8
}
if ($report.status -eq 'failed') { exit 1 }
$global:LASTEXITCODE = 0
