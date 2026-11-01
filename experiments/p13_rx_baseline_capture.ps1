param(
    [string]$Port = 'COM9',
    [Parameter(Mandatory)][string]$LoginPassword,
    [string]$Stem = ('p13-rx-baseline-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
)
# Read-only RX baseline for the running P201, executed as ONE serial session.
#
# Why one session: the compact results are gzipped into a timestamped /tmp name whose sha256 only
# exists after the board produces it, so upload, execution and retrieval must share a session.
#
# What it does, in order:
#   1. validate the two prepared ARM binaries against results/p07b-arm-spectrum-.../SHA256SUMS on the host;
#   2. log in, confirm `Linux pzp201 ... armv7l`, and snapshot the pre-run read-only IIO state;
#   3. upload bin/arm-rx-probe and bin/arm-spectrum into /tmp/<stem>/bin (base64 via BusyBox uudecode);
#   4. re-verify both uploaded binaries by sha256 ON THE BOARD;
#   5. run arm-rx-probe  -> bounded RX snapshots (8x4096 and 4x1024 complex samples);
#   6. run arm-spectrum on each saved capture -> independent software PSD + ROI/summary JSON;
#   7. snapshot the post-run read-only IIO state and diff it against the pre-run snapshot;
#   8. gzip a fixed whitelist of artifacts, sha256 on the board, then read them back as hex, verifying
#      size, transfer sha256, decompression, and the sha256 of the decompressed bytes.
#
# Safety envelope (enforced in this file, not merely documented):
#   * no RF attribute write anywhere: no sampling_frequency / gain / LO / bandwidth / port write,
#     no DDS, no BIST, no loopback, no enable; arm-rx-probe additionally refuses non-zero BIST/loopback;
#   * nothing is transmitted: arm-spectrum only reads a file that was already on the board;
#   * every board path is /tmp/<validated stem>/... and every directory is created with `test ! -e`;
#   * the only board-side deletion is the single directory this run created, removed in cleanup;
#   * no firmware, boot, device-tree, SD, FPGA or Git change.
#
# Windows PowerShell 5.1 / .NET Framework 4.0 compatible on purpose.
$ErrorActionPreference = 'Stop'

if ($Stem -notmatch '^p13-rx-baseline-[a-z0-9-]{4,40}$') { throw "Stem must look like p13-rx-baseline-<suffix>; got '$Stem'" }
$root = Split-Path -Parent $PSScriptRoot
$bundle = Join-Path $root 'results\p07b-arm-spectrum-20261011T060307Z\arm-spectrum-20261011T060307Z'
$probePath = Join-Path $bundle 'bin\arm-rx-probe'
$spectrumPath = Join-Path $bundle 'bin\arm-spectrum'
$evidence = Join-Path $root ('results\' + $Stem)
if (Test-Path -LiteralPath $evidence) { throw "Evidence directory already exists: $evidence" }
foreach ($needed in @($probePath,$spectrumPath,(Join-Path $bundle 'SHA256SUMS'))) {
    if (-not (Test-Path -LiteralPath $needed)) { throw "Missing prepared artifact: $needed" }
}

function Get-Sha256Hex([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes)) -replace '-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function ConvertFrom-Hex([string]$Hex) {
    if ($Hex.Length % 2 -ne 0) { throw 'Hex payload has an odd number of digits.' }
    $out = New-Object byte[] ($Hex.Length / 2)
    for ($i = 0; $i -lt $out.Length; $i++) { $out[$i] = [Convert]::ToByte($Hex.Substring($i*2,2),16) }
    return $out
}
function Get-Hex([string]$Text) {
    $found = [regex]::Matches($Text,'(?m)^[ \t]*(?:[0-9a-f]{2}[ \t]+)*[0-9a-f]{2}[ \t]*\r?$')
    $hex = [Text.StringBuilder]::new()
    foreach ($line in $found) { [void]$hex.Append(($line.Value -replace '\s','')) }
    return $hex.ToString()
}

$probeBytes = [IO.File]::ReadAllBytes($probePath)
$spectrumBytes = [IO.File]::ReadAllBytes($spectrumPath)
$probeHash = Get-Sha256Hex $probeBytes
$spectrumHash = Get-Sha256Hex $spectrumBytes
$recorded = @{}
foreach ($line in (Get-Content -LiteralPath (Join-Path $bundle 'SHA256SUMS'))) {
    $m = [regex]::Match($line,'^([0-9a-f]{64})\s+\*?(.+)$')
    if ($m.Success) { $recorded[$m.Groups[2].Value.Trim()] = $m.Groups[1].Value }
}
if ($recorded['bin/arm-rx-probe'] -ne $probeHash) { throw 'arm-rx-probe does not match its recorded SHA256SUMS entry.' }
if ($recorded['bin/arm-spectrum'] -ne $spectrumHash) { throw 'arm-spectrum does not match its recorded SHA256SUMS entry.' }
Write-Host "PREPARED_ARTIFACTS_OK probe=$probeHash spectrum=$spectrumHash"

New-Item -ItemType Directory -Path $evidence | Out-Null
$scriptBytes = [IO.File]::ReadAllBytes($PSCommandPath)
[IO.File]::WriteAllBytes((Join-Path $evidence 'driver-used.ps1'),$scriptBytes)

$boardRoot = '/tmp/' + $Stem
$boardBin = $boardRoot + '/bin'
$boardCapture = $boardRoot + '/capture'
$boardSpectrum = $boardRoot + '/spectrum'
$boardPack = $boardRoot + '/pack'
$boardGzip = $boardPack + '/baseline.tar.gz'
$artifacts = @('capture/session-1.iq','capture/session-1.json','capture/session-2.iq','capture/session-2.json',
               'spectrum/session-1.json','spectrum/session-2.json','iio-before.txt','iio-after.txt','run.txt')
$packList = ($artifacts | ForEach-Object { $boardRoot + '/' + $_ }) -join ' '

$serial = [IO.Ports.SerialPort]::new($Port,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 1000
$serial.WriteTimeout = 15000
$transcript = [Text.StringBuilder]::new()
$stages = [Collections.Generic.List[object]]::new()
$report = [ordered]@{
    started_at = (Get-Date).ToString('o'); port = $Port; stem = $Stem
    board_root = $boardRoot; evidence = $evidence; status = 'running'; stages = $stages
    access = 'read_only_no_RF_writes_no_TX_no_firmware_change'
    prepared_arm_rx_probe_sha256 = $probeHash; prepared_arm_spectrum_sha256 = $spectrumHash
    driver_source_sha256 = Get-Sha256Hex $scriptBytes
    rf_operations = $false; firmware_changes = $false; git_operations = $false
}
function Wait-Serial([string]$Pattern,[int]$Seconds = 20) {
    $buffer = [Text.StringBuilder]::new()
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) { [void]$buffer.Append($chunk); [void]$transcript.Append($chunk) }
        if ($buffer.Length -gt 67108864) { throw 'Serial response exceeded 64 MiB safety limit.' }
        if ($buffer.ToString() -match $Pattern) { return $buffer.ToString() }
        Start-Sleep -Milliseconds 30
    }
    throw "Serial response timed out waiting for $Pattern"
}
function Invoke-Board([string]$Name,[string]$Command,[int]$Seconds = 30) {
    $marker = '__P13B_' + [guid]::NewGuid().ToString('N') + '__'
    [void]$transcript.AppendLine("`n[STAGE $Name]")
    $serial.Write($Command + '; printf ''\n' + $marker + ':%s\n'' "$?"' + "`r")
    $output = Wait-Serial ('(?m)^' + $marker + ':(\d+)\r?$') $Seconds
    $code = [int][regex]::Match($output,('(?m)^' + $marker + ':(\d+)\r?$')).Groups[1].Value
    $stages.Add([ordered]@{ name = $Name; command = $Command; exit_code = $code; output = $output })
    Write-Host "STAGE $Name exit=$code"
    if ($code -ne 0) { throw "Board stage $Name failed with exit $code" }
    return $output
}
function Send-File([string]$Name,[byte[]]$Payload,[string]$BoardPath) {
    $begin = '__P13B_UP_BEGIN_' + [guid]::NewGuid().ToString('N') + '__'
    $done = '__P13B_UP_DONE_' + [guid]::NewGuid().ToString('N') + '__'
    [void]$transcript.AppendLine("`n[UPLOAD $Name -> $BoardPath]")
    $wire = 'printf ''\n' + $begin + '\n''; uudecode -o ' + $BoardPath + '; printf ''\n' + $done + ':%s\n'' "$?"'
    $serial.Write($wire + "`r")
    $null = Wait-Serial ('(?m)^' + $begin + '\r?$') 20
    $serial.Write("begin-base64 755 $Name`n")
    $base64 = [Convert]::ToBase64String($Payload)
    $lines = [Text.StringBuilder]::new()
    for ($i = 0; $i -lt $base64.Length; $i += 76) {
        [void]$lines.Append($base64.Substring($i,[Math]::Min(76,$base64.Length - $i)))
        [void]$lines.Append("`n")
    }
    $stream = $lines.ToString()
    $tail = ''
    $timer = [Diagnostics.Stopwatch]::StartNew()
    for ($i = 0; $i -lt $stream.Length; $i += 4096) {
        if ($timer.Elapsed.TotalSeconds -gt 600) { throw 'Upload exceeded 10 minutes.' }
        $part = $serial.ReadExisting()
        if ($part) {
            [void]$transcript.Append($part); $tail += $part
            if ($tail.Length -gt 256) { $tail = $tail.Substring($tail.Length - 200) }
            if ($tail.Contains($done)) { throw 'Decoder exited before the payload was fully sent.' }
        }
        while ($serial.BytesToWrite -gt 8192) { Start-Sleep -Milliseconds 25 }
        $serial.Write($stream.Substring($i,[Math]::Min(4096,$stream.Length - $i)))
    }
    $serial.Write("====`n")
    $end = Wait-Serial ('(?m)^' + $done + ':(\d+)\r?$') 30
    $code = [int][regex]::Match($end,('(?m)^' + $done + ':(\d+)\r?$')).Groups[1].Value
    if ($code -ne 0) { throw "uudecode exited $code for $Name" }
    $stages.Add([ordered]@{ name = ('upload-' + $Name); command = "uudecode -> $BoardPath"; exit_code = 0
                            output = ''; wire_bytes = $stream.Length; payload_bytes = $Payload.Length
                            payload_sha256 = (Get-Sha256Hex $Payload) })
    Write-Host "UPLOADED $Name bytes=$($Payload.Length) wire=$($stream.Length)"
}
$iioProbe = 'for d in /sys/bus/iio/devices/iio:device*; do test -r "$d/name" || continue; n=$(cat "$d/name"); case "$n" in ad9361-phy|cf-ad9361-dds-core-lpc|cf-ad9361-lpc) printf "DEVICE %s %s\n" "$d" "$n"; for a in "$d"/*sampling_frequency "$d"/*rf_bandwidth "$d"/*hardwaregain "$d"/*rf_port_select "$d"/*gain_control_mode "$d"/*_LO_frequency; do test -r "$a" || continue; printf "%s=" "$a"; cat "$a"; done ;; esac; done'
try {
    $serial.Open()
    $serial.Write("`r")
    $initial = Wait-Serial '(?m)(login:\s*$|#\s*$)' 12
    if ($initial -match 'login:\s*$') {
        $serial.Write("root`r")
        $null = Wait-Serial '(?i)password:\s*$' 12
        $serial.Write($LoginPassword + "`r")
        $authenticated = Wait-Serial '(?m)(#\s*$|login:\s*$)' 15
        if ($authenticated -notmatch '(?m)#\s*$') { throw 'Documented vendor login was rejected; no retry.' }
        $report.authentication = 'documented_vendor_account_via_serial'
    }
    $identity = Invoke-Board 'identity' 'uname -a'
    if ($identity -notmatch 'Linux pzp201 .*armv7l') { throw 'Unexpected board identity; stopping before anything is uploaded or run.' }
    $bootId = Invoke-Board 'boot-id' 'cat /proc/sys/kernel/random/boot_id'
    $report.board_boot_id = [regex]::Match($bootId,'(?m)^([0-9a-f-]{36})\r?$').Groups[1].Value
    $before = Invoke-Board 'iio-before' $iioProbe
    $null = Invoke-Board 'make-dirs' "mkdir $boardRoot && mkdir $boardBin $boardCapture $boardSpectrum $boardPack"
    Send-File 'arm-rx-probe' $probeBytes ($boardBin + '/arm-rx-probe')
    Send-File 'arm-spectrum' $spectrumBytes ($boardBin + '/arm-spectrum')
    $verified = Invoke-Board 'verify-uploaded' "cd $boardBin && chmod 755 arm-rx-probe arm-spectrum && sha256sum arm-rx-probe arm-spectrum"
    if ($verified -notmatch [regex]::Escape($probeHash)) { throw 'Uploaded arm-rx-probe sha256 mismatch on the board.' }
    if ($verified -notmatch [regex]::Escape($spectrumHash)) { throw 'Uploaded arm-spectrum sha256 mismatch on the board.' }
    $report.uploaded_binaries_verified_on_board = $true
    $capture = Invoke-Board 'run-arm-rx-probe' ("cd $boardRoot && ./bin/arm-rx-probe $boardCapture 2>&1 | tee $boardRoot/run.txt") 180
    if ($capture -notmatch 'ARM_RX_SESSION_PASS session=1 blocks=8 samples=32768') { throw 'Session 1 pass marker missing.' }
    if ($capture -notmatch 'ARM_RX_SESSION_PASS session=2 blocks=4 samples=4096') { throw 'Session 2 pass marker missing.' }
    if ($capture -notmatch 'ARM_RX_CONTEXT_RELEASED status=0') { throw 'RX context was not released cleanly.' }
    foreach ($session in 1,2) {
        $null = Invoke-Board ("run-arm-spectrum-$session") ("cd $boardRoot && ./bin/arm-spectrum $boardCapture/session-$session.iq $boardSpectrum/session-$session 30720000")
    }
    $after = Invoke-Board 'iio-after' $iioProbe
    $report.iio_state_unchanged = ([regex]::Match($before,'(?s)DEVICE.*').Value.Trim() -eq [regex]::Match($after,'(?s)DEVICE.*').Value.Trim())
    if (-not $report.iio_state_unchanged) { throw 'Read-only IIO state changed across the capture; refusing to treat it as a clean baseline.' }
    $null = Invoke-Board 'pack' ("cd $boardRoot && tar -czf $boardGzip $packList")
    $packHashOut = Invoke-Board 'pack-checksum' "sha256sum $boardGzip"
    $packHash = [regex]::Match($packHashOut,'(?m)^([0-9a-f]{64})\s').Groups[1].Value.ToLowerInvariant()
    $packSizeOut = Invoke-Board 'pack-size' "wc -c < $boardGzip"
    $packSize = [int][regex]::Match($packSizeOut,'(?m)^\s*(\d+)\s*\r?$').Groups[1].Value
    if ($packHash -notmatch '^[0-9a-f]{64}$') { throw 'Missing board pack sha256.' }
    if ($packSize -lt 1 -or $packSize -gt 4194304) { throw "Board pack is $packSize bytes; outside the 1 byte..4 MiB readback bound." }
    $report.board_pack_sha256 = $packHash
    $report.board_pack_bytes = $packSize
    Write-Host "PACK bytes=$packSize sha256=$packHash"
    $encoded = Invoke-Board 'readback' "od -An -v -tx1 $boardGzip" 600
    $hex = Get-Hex $encoded
    if (-not $hex) { throw 'No hex payload recovered.' }
    $bytes = ConvertFrom-Hex $hex
    if ($bytes.Length -ne $packSize) { throw "Readback size mismatch: $($bytes.Length) vs $packSize" }
    $transferHash = Get-Sha256Hex $bytes
    if ($transferHash -ne $packHash) { throw "Transfer sha256 mismatch: $transferHash" }
    $gzPath = Join-Path $evidence 'baseline.tar.gz'
    [IO.File]::WriteAllBytes($gzPath,$bytes)
    $report.transfer_sha256 = $transferHash
    $report.transfer_bytes = $bytes.Length
    $report.local_gzip = $gzPath
    $null = Invoke-Board 'cleanup' "rm -rf $boardRoot"
    $report.board_workspace_removed = $true
    $report.status = 'baseline_captured_readback_checksum_passed'
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
    Write-Host ('FAILED: ' + $_.Exception.Message)
} finally {
    if ($serial.IsOpen) {
        try { $null = Invoke-Board 'shell-alive' 'true' 10 } catch { $report.shell_check_error = $_.Exception.Message }
        $serial.Close()
    }
    $serial.Dispose()
    $report.finished_at = (Get-Date).ToString('o')
    $transcript.ToString() | Set-Content -LiteralPath (Join-Path $evidence 'serial-transcript.txt') -Encoding utf8
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'report.json') -Encoding utf8
}
if ($report.status -eq 'failed') { exit 1 }
