param(
    [string]$Port = 'COM9',
    [Parameter(Mandatory)][string]$EvidenceDirectory,
    [Parameter(Mandatory)][string]$LoginPassword,
    [Parameter(Mandatory)][string]$BoardFile,
    [Parameter(Mandatory)][int]$ExpectedBytes,
    [string]$LocalName,
    [switch]$GzipOnBoard,
    [ValidateRange(30,900)][int]$ReadbackSeconds = 300
)
# Read one bounded regular file back over the serial console as hex, then verify size and SHA256.
# Read-only with respect to the board: it only reads an existing file, gzips into /tmp, and cleans up
# that single temporary copy. It never writes RF attributes, never creates IIO buffers, never transmits.
# The remote path and every intermediate path are validated before any command is sent.
#
# Compatibility: written for Windows PowerShell 5.1 / .NET Framework 4.0 on purpose. That runtime has no
# [Security.Cryptography.SHA256]::HashData and no [Convert]::FromHexString, so this file uses
# SHA256.Create()+ComputeHash and a local hex decoder instead. Do not swap them back.
$ErrorActionPreference = 'Stop'
if ($BoardFile -notmatch '^/tmp/[A-Za-z0-9._/-]+$' -or $BoardFile -match '\.\.') { throw 'Remote file must be an explicit /tmp path.' }
if ($ExpectedBytes -lt 1 -or $ExpectedBytes -gt 4194304) { throw 'Readback limited to 4 MiB.' }
if (Test-Path -LiteralPath $EvidenceDirectory) { throw 'Evidence directory already exists; refusing overwrite.' }
New-Item -ItemType Directory -Path $EvidenceDirectory | Out-Null

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

$scriptBytes = [IO.File]::ReadAllBytes($PSCommandPath)
[IO.File]::WriteAllBytes((Join-Path $EvidenceDirectory 'readback-used.ps1'), $scriptBytes)
if (-not $LocalName) { $LocalName = Split-Path -Leaf $BoardFile }
$suffix = if ($GzipOnBoard) { '.gz' } else { '' }
$stem = 'p13-readback-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$boardCopy = '/tmp/' + $stem + ([IO.Path]::GetFileName($BoardFile)) + $suffix
$serial = [IO.Ports.SerialPort]::new($Port,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 1000
$serial.WriteTimeout = 15000
$transcript = [Text.StringBuilder]::new()
$stages = [Collections.Generic.List[object]]::new()
$report = [ordered]@{
    started_at = (Get-Date).ToString('o'); port = $Port; board_file = $BoardFile
    board_copy = $boardCopy; expected_bytes = $ExpectedBytes; gzip_on_board = [bool]$GzipOnBoard
    status = 'running'; stages = $stages
    read_only = $true; rf_operations = $false; firmware_changes = $false
    readback_used_source_sha256 = Get-Sha256Hex $scriptBytes
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
    $marker = '__P13_' + [guid]::NewGuid().ToString('N') + '__'
    [void]$transcript.AppendLine("`n[STAGE $Name]")
    $serial.Write($Command + '; printf ''\n' + $marker + ':%s\n'' "$?"' + "`r")
    $output = Wait-Serial ('(?m)^' + $marker + ':(\d+)\r?$') $Seconds
    $code = [int][regex]::Match($output,('(?m)^' + $marker + ':(\d+)\r?$')).Groups[1].Value
    $stages.Add([ordered]@{ name = $Name; command = $Command; exit_code = $code; output = $output })
    Write-Host "STAGE $Name exit=$code"
    if ($code -ne 0) { throw "Board stage $Name failed with exit $code" }
    return $output
}
function Get-Hex([string]$Text) {
    $found = [regex]::Matches($Text,'(?m)^[ \t]*(?:[0-9a-f]{2}[ \t]+)*[0-9a-f]{2}[ \t]*\r?$')
    $hex = [Text.StringBuilder]::new()
    foreach ($line in $found) { [void]$hex.Append(($line.Value -replace '\s','')) }
    return $hex.ToString()
}
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
    if ($identity -notmatch 'Linux pzp201 .*armv7l') { throw 'Unexpected board identity; stopping before any read.' }
    $null = Invoke-Board 'source-present' "test -f $BoardFile"
    $sizeOut = Invoke-Board 'source-size' "wc -c < $BoardFile"
    $size = [int][regex]::Match($sizeOut,'(?m)^\s*(\d+)\s*\r?$').Groups[1].Value
    if ($size -ne $ExpectedBytes) { throw "Board file size $size != expected $ExpectedBytes" }
    $hashOut = Invoke-Board 'source-checksum' "sha256sum $BoardFile"
    $sourceHash = [regex]::Match($hashOut,'(?m)^([0-9a-f]{64})\s').Groups[1].Value.ToLowerInvariant()
    if ($sourceHash -notmatch '^[0-9a-f]{64}$') { throw 'Missing source SHA256.' }
    $report.board_source_sha256 = $sourceHash
    $report.board_source_bytes = $size
    if ($GzipOnBoard) {
        $null = Invoke-Board 'board-gzip' "gzip -c $BoardFile > $boardCopy"
        $copyHashOut = Invoke-Board 'copy-checksum' "sha256sum $boardCopy"
        $copySizeOut = Invoke-Board 'copy-size' "wc -c < $boardCopy"
        $copySize = [int][regex]::Match($copySizeOut,'(?m)^\s*(\d+)\s*\r?$').Groups[1].Value
        $report.board_copy_sha256 = [regex]::Match($copyHashOut,'(?m)^([0-9a-f]{64})\s').Groups[1].Value.ToLowerInvariant()
    } else {
        $null = Invoke-Board 'copy-file' "cp $BoardFile $boardCopy"
        $report.board_copy_sha256 = $sourceHash
        $copySize = $size
    }
    $report.board_copy_bytes = $copySize
    if ($copySize -lt 1 -or $copySize -gt 4194304) { throw "Readback payload $copySize bytes is out of the 4 MiB bound." }
    Write-Host "READBACK bytes=$copySize sha256=$($report.board_copy_sha256)"
    $encoded = Invoke-Board 'readback' "od -An -v -tx1 $boardCopy" $ReadbackSeconds
    $hex = Get-Hex $encoded
    if (-not $hex) { throw 'No hex payload was recovered from the od output.' }
    $bytes = ConvertFrom-Hex $hex
    if ($bytes.Length -ne $copySize) { throw "Readback size mismatch: $($bytes.Length) vs $copySize" }
    $actualHash = Get-Sha256Hex $bytes
    if ($actualHash -ne $report.board_copy_sha256) { throw "Readback SHA256 mismatch: $actualHash" }
    $report.transferred_payload_sha256 = $actualHash
    $target = Join-Path $EvidenceDirectory $LocalName
    if ($GzipOnBoard) {
        $gzPath = Join-Path $EvidenceDirectory ($LocalName + '.gz')
        [IO.File]::WriteAllBytes($gzPath,$bytes)
        $report.local_gzip = $gzPath
        $gzFile = [IO.File]::OpenRead($gzPath)
        try {
            $inflate = [IO.Compression.GZipStream]::new($gzFile,[IO.Compression.CompressionMode]::Decompress)
            try { $plain = [IO.MemoryStream]::new(); $inflate.CopyTo($plain); $plainBytes = $plain.ToArray() }
            finally { $inflate.Dispose() }
        } finally { $gzFile.Dispose() }
        if ($plainBytes.Length -ne $size) { throw "Decompressed size $($plainBytes.Length) != board source size $size" }
        $plainHash = Get-Sha256Hex $plainBytes
        if ($plainHash -ne $sourceHash) { throw 'Decompressed SHA256 does not match the board source file.' }
        [IO.File]::WriteAllBytes($target,$plainBytes)
        $report.decompressed_bytes = $plainBytes.Length
        $report.decompressed_sha256 = $plainHash
        $report.decompressed_matches_board_source = $true
    } else {
        [IO.File]::WriteAllBytes($target,$bytes)
    }
    $report.local_file = $target
    $report.local_bytes = (Get-Item -LiteralPath $target).Length
    $null = Invoke-Board 'cleanup-board-copy' "rm -f $boardCopy"
    $report.cleanup_removed_board_copy = $true
    $report.status = 'readback_checksum_passed'
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
    Write-Host ('FAILED: ' + $_.Exception.Message)
} finally {
    if ($serial.IsOpen) {
        try { $null = Invoke-Board 'shell-alive' 'true' 10 }
        catch { $report.shell_check_error = $_.Exception.Message }
        $serial.Close()
    }
    $serial.Dispose()
    $report.finished_at = (Get-Date).ToString('o')
    $transcript.ToString() | Set-Content -LiteralPath (Join-Path $EvidenceDirectory 'serial-transcript.txt') -Encoding utf8
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $EvidenceDirectory 'report.json') -Encoding utf8
}
if ($report.status -eq 'failed') { exit 1 }
