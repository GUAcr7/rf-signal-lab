param(
    [string]$Port = 'COM9',
    [Parameter(Mandatory)][string]$InputFile,
    [Parameter(Mandatory)][string]$ExpectedSha256,
    [Parameter(Mandatory)][string]$BoardDirectory,
    [Parameter(Mandatory)][string]$EvidenceDirectory,
    [Parameter(Mandatory)][string]$LoginPassword
)
# Stream a checked gzip through BusyBox uudecode. Does not extract/run code.
#
# Compatibility note (2026-10-16): the original revision of this tool used
# [Security.Cryptography.SHA256]::HashData and [Convert]::ToHexString. Those APIs exist only in
# .NET 5+; this host's only PowerShell is Windows PowerShell 5.1 on .NET Framework 4.0, where they
# throw "does not contain a method named 'HashData'". The calls are therefore expressed with
# SHA256.Create()+ComputeHash and BitConverter, which work on both runtimes.
$ErrorActionPreference = 'Stop'
function Get-Sha256Hex([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes)) -replace '-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
if ($BoardDirectory -notmatch '^/tmp/p12-source-stage-[a-z0-9-]+$') { throw 'New explicit task /tmp directory required.' }
if ($ExpectedSha256 -notmatch '^[0-9a-f]{64}$') { throw 'Expected SHA256 required.' }
$inputPath = (Resolve-Path -LiteralPath $InputFile).Path
$payload = [IO.File]::ReadAllBytes($inputPath)
if ($payload.Length -lt 1 -or $payload.Length -gt 4194304) { throw 'Transfer limited to 4 MiB.' }
$actualHash = Get-Sha256Hex $payload
if ($actualHash -ne $ExpectedSha256) { throw 'Host payload changed.' }
if (Test-Path -LiteralPath $EvidenceDirectory) { throw 'Evidence exists; never overwrite.' }
New-Item -ItemType Directory -Path $EvidenceDirectory | Out-Null
$uploaderBytes = [IO.File]::ReadAllBytes($PSCommandPath)
[IO.File]::WriteAllBytes((Join-Path $EvidenceDirectory 'uploader-used.ps1'), $uploaderBytes)
$serial = [IO.Ports.SerialPort]::new($Port,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.WriteTimeout = 15000
$serial.ReadTimeout = 1000
$transcript = [Text.StringBuilder]::new()
$report = [ordered]@{status='running'; port=$Port; input_sha256=$actualHash; input_bytes=$payload.Length; board_directory=$BoardDirectory; board_file=($BoardDirectory+'/source.tar.gz'); rf_operations=$false; firmware_changes=$false; tty_restored=$false; started_at=(Get-Date).ToString('o')}
$report.uploader_source_sha256 = Get-Sha256Hex $uploaderBytes
$savedTty = $null
$receiving = $false
function Wait-Match([string]$Pattern,[int]$Seconds=15) {
    $received = [Text.StringBuilder]::new()
    $until = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $until) {
        $part = $serial.ReadExisting()
        if ($part) { [void]$received.Append($part); [void]$transcript.Append($part) }
        if ($received.ToString() -match $Pattern) { return $received.ToString() }
        Start-Sleep -Milliseconds 30
    }
    throw "Serial timeout waiting for $Pattern"
}
function Board-Command([string]$Command,[int]$Seconds=15) {
    $marker = '__P12_' + [guid]::NewGuid().ToString('N') + '__'
    $serial.Write($Command + '; printf ''\n' + $marker + ':%s\n'' "$?"' + "`r")
    $result = Wait-Match ('(?m)^'+$marker+':(\d+)\r?$') $Seconds
    $match = [regex]::Match($result,('(?m)^'+$marker+':(\d+)\r?$'))
    if ([int]$match.Groups[1].Value -ne 0) { throw "Board command failed: $Command" }
    return $result
}
try {
    $serial.Open()
    $serial.Write("`r")
    $prompt = Wait-Match '(?m)(login:\s*$|#\s*$)'
    if ($prompt -match 'login:\s*$') {
        $serial.Write("root`r")
        $null = Wait-Match '(?i)password:\s*$'
        $serial.Write($LoginPassword + "`r")
        $null = Wait-Match '(?m)#\s*$'
    }
    $identity = Board-Command 'uname -a'
    if ($identity -notmatch 'Linux pzp201 .*armv7l') { throw 'Unexpected target identity.' }
    $tty = Board-Command 'stty -g'
    $match = [regex]::Match($tty,'(?m)^([0-9a-f]+(?::[0-9a-f]+){10,})\r?$')
    if (-not $match.Success) { throw 'Cannot preserve original TTY mode.' }
    $savedTty = $match.Groups[1].Value
    $null = Board-Command ("test ! -e $BoardDirectory && mkdir $BoardDirectory")
    $null = Board-Command 'stty -echo'
    $begin = '__P12_UPLOAD_BEGIN_' + [guid]::NewGuid().ToString('N') + '__'
    $done = '__P12_UPLOAD_DONE_' + [guid]::NewGuid().ToString('N') + '__'
    $wire = 'printf ''\n' + $begin + '\n''; uudecode -o ' + $BoardDirectory + '/source.tar.gz; printf ''\n' + $done + ':%s\n'' "$?"'
    $serial.Write($wire + "`r")
    $null = Wait-Match ('(?m)^'+$begin+'\r?$')
    $receiving = $true
    $serial.Write("begin-base64 600 source.tar.gz`n")
    $base64 = [Convert]::ToBase64String($payload)
    $lines = [Text.StringBuilder]::new()
    for ($i=0; $i -lt $base64.Length; $i+=76) {
        [void]$lines.Append($base64.Substring($i,[Math]::Min(76,$base64.Length-$i)))
        [void]$lines.Append("`n")
    }
    $stream = $lines.ToString()
    $decoderTail = ''
    $lastProgress = Get-Date
    $timer = [Diagnostics.Stopwatch]::StartNew()
    for ($i=0; $i -lt $stream.Length; $i+=4096) {
        $part = $serial.ReadExisting()
        if ($part) {
            [void]$transcript.Append($part)
            $decoderTail += $part
            if ($decoderTail.Length -gt $done.Length+64) { $decoderTail = $decoderTail.Substring($decoderTail.Length-$done.Length-64) }
            if ($decoderTail.Contains($done)) { throw 'Decoder exited before full transfer; stopping payload.' }
        }
        if ($timer.Elapsed.TotalSeconds -gt 420) { throw 'Transfer exceeded 7 minutes.' }
        while ($serial.BytesToWrite -gt 8192) {
            if ($timer.Elapsed.TotalSeconds -gt 420) { throw 'Transfer queue stalled beyond 7 minutes.' }
            $part = $serial.ReadExisting()
            if ($part) {
                [void]$transcript.Append($part)
                $decoderTail += $part
                if ($decoderTail.Length -gt $done.Length+64) { $decoderTail = $decoderTail.Substring($decoderTail.Length-$done.Length-64) }
                if ($decoderTail.Contains($done)) { throw 'Decoder exited while transfer queue was draining.' }
            }
            Start-Sleep -Milliseconds 30
        }
        $serial.Write($stream.Substring($i,[Math]::Min(4096,$stream.Length-$i)))
        if (((Get-Date)-$lastProgress).TotalSeconds -ge 20) {
            Write-Host ('UPLOAD {0:N1}% ({1:N0}/{2:N0} wire bytes)' -f (100.0*$i/$stream.Length),$i,$stream.Length)
            $lastProgress = Get-Date
        }
    }
    $serial.Write("====`n")
    $end = Wait-Match ('(?m)^'+$done+':(\d+)\r?$') 30
    $receiving = $false
    $code = [int][regex]::Match($end,('(?m)^'+$done+':(\d+)\r?$')).Groups[1].Value
    if ($code -ne 0) { throw "Uudecode exit $code" }
    $checksum = Board-Command ('sha256sum ' + $BoardDirectory + '/source.tar.gz')
    if ($checksum -notmatch ('(?m)^'+$ExpectedSha256+'\s+'+[regex]::Escape($BoardDirectory+'/source.tar.gz')+'\r?$')) { throw 'Transferred file SHA256 mismatch.' }
    $report.status = 'serial_upload_checksum_passed_no_code_executed'
    $report.wire_payload_bytes = $stream.Length
    $report.transfer_seconds = $timer.Elapsed.TotalSeconds
    Write-Host ('UPLOAD_PASS sha256=' + $ExpectedSha256)
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
    Write-Host ('FAILED: ' + $_.Exception.Message)
} finally {
    if ($serial.IsOpen) {
        try {
            if ($receiving) {
                $serial.DiscardOutBuffer()
                $serial.Write([string][char]3)
                $null = Wait-Match '(?m)#\s*$' 5
                $receiving = $false
            }
            if ($savedTty) {
                $null = Board-Command ('stty ' + $savedTty)
                $restored = Board-Command 'stty -g'
                $report.tty_restored = $restored -match ('(?m)^'+[regex]::Escape($savedTty)+'\r?$')
            }
        } catch { $report.tty_restore_error = $_.Exception.Message }
        $serial.Close()
    }
    $serial.Dispose()
    $report.finished_at = (Get-Date).ToString('o')
    $transcript.ToString() | Set-Content -LiteralPath (Join-Path $EvidenceDirectory 'serial-transcript.txt') -Encoding utf8
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $EvidenceDirectory 'report.json') -Encoding utf8
}
if ($report.status -eq 'failed' -or -not $report.tty_restored) { exit 1 }
