# Read only the matching Microsoft update payload; no services/ACL/policy changes.
$ErrorActionPreference = 'Stop'
$taskNetFxOut = 'E:/FPGA_Tools/Downloads/NetFx3-System-20261025T121739Z/source'
$taskNetFxExpected = [Convert]::ToHexString([Convert]::FromBase64String('3Dr5OvXGTcEVQJQ30xAYuvLDxGFngGpZkSS8kFrlEvY=')).ToLowerInvariant()
$taskNetFxReport = [ordered]@{status='searching_protected_matching_update_cache'; bytes=71321276; expected_sha256=$taskNetFxExpected; copied=$false; system_changes=$false}
try {
    $taskNetFxRoots = @(
        'C:/Windows/ServiceProfiles/NetworkService/AppData/Local/Microsoft/Windows/DeliveryOptimization/Cache',
        'C:/Windows/SoftwareDistribution/Download'
    )
    foreach ($taskNetFxRoot in $taskNetFxRoots) {
        if (!(Test-Path -LiteralPath $taskNetFxRoot)) { continue }
        $taskNetFxCandidates = @(Get-ChildItem -LiteralPath $taskNetFxRoot -File -Recurse -ErrorAction SilentlyContinue | Where-Object Length -eq 71321276 | Select-Object -First 20)
        foreach ($taskNetFxFile in $taskNetFxCandidates) {
            $taskNetFxStream = [IO.File]::Open($taskNetFxFile.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
            try {
                $taskNetFxMemory = [IO.MemoryStream]::new()
                try {
                    $taskNetFxStream.CopyTo($taskNetFxMemory)
                    $taskNetFxBytes = $taskNetFxMemory.ToArray()
                } finally { $taskNetFxMemory.Dispose() }
            } finally { $taskNetFxStream.Dispose() }
            $taskNetFxHasher = [Security.Cryptography.SHA256]::Create()
            try { $taskNetFxHash = [Convert]::ToHexString($taskNetFxHasher.ComputeHash($taskNetFxBytes)).ToLowerInvariant() }
            finally { $taskNetFxHasher.Dispose() }
            if ($taskNetFxHash -ne $taskNetFxExpected) { continue }
            $taskNetFxDest = Join-Path $taskNetFxOut 'Microsoft-Windows-NetFx3-OnDemand-Package~31bf3856ad364e35~amd64~~.cab'
            if (Test-Path -LiteralPath $taskNetFxDest) { throw 'Destination already exists; refusing overwrite' }
            [IO.File]::WriteAllBytes($taskNetFxDest, $taskNetFxBytes)
            if ((Get-FileHash -LiteralPath $taskNetFxDest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskNetFxExpected) { throw 'Copy hash mismatch' }
            $taskNetFxReport.status = 'verified_matching_Microsoft_payload_saved_to_E'
            $taskNetFxReport.copied = $true
            $taskNetFxReport.source = $taskNetFxFile.FullName
            $taskNetFxReport.destination = $taskNetFxDest
            break
        }
        if ($taskNetFxReport.copied) { break }
    }
    if (!$taskNetFxReport.copied) { $taskNetFxReport.status = 'matching_payload_not_accessible_as_complete_file' }
} catch {
    $taskNetFxReport.status = 'cache_copy_failed'
    $taskNetFxReport.error = $_.Exception.Message
}
$taskNetFxReport.completed_local = (Get-Date -Format o)
$taskNetFxReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskNetFxOut 'cache-copy-report.json') -Encoding UTF8
