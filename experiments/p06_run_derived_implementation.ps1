param([string]$Script,[string]$Name)
$ErrorActionPreference='Stop'
$root=(Resolve-Path "$PSScriptRoot/..").Path
$inputDcp='E:/FPGA_Tools/Work/p06-pzp201-20261011c/hdl/projects/pzp201/pzp201.runs/impl_1/system_top_opt.dcp'
$expected='9A4B4F58E6AA0E545258B6D3ED8A4CB9855F27B7D466D44020BD73F590306E2B'
if((Get-FileHash -LiteralPath $inputDcp -Algorithm SHA256).Hash -ne $expected){throw 'Original checkpoint differs'}
if($Name -notmatch '^p06-[a-z0-9-]+$'){throw 'Invalid experiment name'}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$work=Join-Path 'E:/FPGA_Tools/Work' "$Name-$stamp"
$evidence=Join-Path $root "results/$Name-$stamp"
if((Test-Path -LiteralPath $work) -or (Test-Path -LiteralPath $evidence)){throw 'Result already exists'}
New-Item -ItemType Directory -Path $work,$evidence | Out-Null
$source=(Resolve-Path -LiteralPath (Join-Path $root $Script)).Path
Copy-Item -LiteralPath $source -Destination "$work/run.tcl"
Copy-Item -LiteralPath $source -Destination "$evidence/run.tcl"
$started=Get-Date -Format o
Push-Location $work
try{& 'E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat' -mode batch -source "$work/run.tcl" -tclargs $inputDcp "$work/reports" *> "$evidence/console.txt"; $nativeExit=$LASTEXITCODE}finally{Pop-Location}
if(Test-Path -LiteralPath "$work/reports"){Copy-Item -LiteralPath "$work/reports" -Destination "$evidence/reports" -Recurse}
$record=[ordered]@{started=$started;ended=(Get-Date -Format o);input=$inputDcp;input_sha256=$expected;input_unchanged=((Get-FileHash -LiteralPath $inputDcp).Hash -eq $expected);script_sha256=(Get-FileHash -LiteralPath $source).Hash;work=$work;evidence=$evidence;exit_code=$nativeExit;bitstream_written=$false;board_accessed=$false;timing_accepted=$false}
$record|ConvertTo-Json|Set-Content -LiteralPath "$evidence/run-record.json" -Encoding utf8
$record|ConvertTo-Json -Compress
exit $nativeExit
