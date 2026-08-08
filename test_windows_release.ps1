$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fail($m) { throw $m }

function Get-PeMachine($Path) {
  $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $Path))
  $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
  return [BitConverter]::ToUInt16($bytes, $peOffset + 4)
}

function Assert-Exists($Path, $Label) {
  if (-not (Test-Path $Path)) { Fail "$Label not found: $Path" }
}

$setup = Join-Path $PSScriptRoot "installer\Enki_Agency_Uniq_2.5.1_Setup.exe"
Assert-Exists $setup "Setup.exe"

$dist = Join-Path $PSScriptRoot "dist\Enki Agency Uniq"
$distExe = Join-Path $dist "Enki Agency Uniq.exe"
Assert-Exists $distExe "PyInstaller EXE"
Assert-Exists (Join-Path $dist "ffmpeg.exe") "dist ffmpeg.exe"
Assert-Exists (Join-Path $dist "ffprobe.exe") "dist ffprobe.exe"

$machine = Get-PeMachine $distExe
if ($machine -ne 0x8664) { Fail "Enki Agency Uniq.exe is not Windows x64. PE machine: 0x$($machine.ToString('x'))" }

$installDir = Join-Path $env:LOCALAPPDATA "Programs\Enki Agency Uniq"
$installedExe = Join-Path $installDir "Enki Agency Uniq.exe"
Assert-Exists $installedExe "installed EXE"
Assert-Exists (Join-Path $installDir "ffmpeg.exe") "installed ffmpeg.exe"
Assert-Exists (Join-Path $installDir "ffprobe.exe") "installed ffprobe.exe"
Assert-Exists (Join-Path $installDir "EnkiAgencyUniq.png") "installed logo"
Assert-Exists (Join-Path $installDir "EnkiAgencyUniq.ico") "installed icon"

$oldPath = $env:PATH
try {
  $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
  $p = Start-Process -FilePath $installedExe -PassThru
  Start-Sleep -Seconds 8
  if ($p.HasExited) { Fail "Installed app exited immediately without system Python. ExitCode=$($p.ExitCode)" }
  if ($p.MainWindowTitle -notlike "Enki Agency Uniq*") { Write-Host "WARN: main window title not visible yet: '$($p.MainWindowTitle)'" }
  Stop-Process -Id $p.Id -Force
}
finally {
  $env:PATH = $oldPath
}

$root = Join-Path $env:USERPROFILE "Videos\Enki Agency Uniq"
foreach ($rel in @("input","output\videos","output\photos","failed")) {
  Assert-Exists (Join-Path $root $rel) "working folder $rel"
}

$testRoot = Join-Path $env:TEMP ("enki_release_test_" + [guid]::NewGuid().ToString("N"))
$inDir = Join-Path $testRoot "input"
$outDir = Join-Path $testRoot "output"
New-Item -ItemType Directory -Force -Path $inDir, $outDir | Out-Null

$ffmpeg = Join-Path $installDir "ffmpeg.exe"
$ffprobe = Join-Path $installDir "ffprobe.exe"
$video = Join-Path $inDir "sample_video.mp4"
$photo = Join-Path $inDir "sample_photo.jpg"

& $ffmpeg -y -hide_banner -loglevel error -f lavfi -i testsrc2=size=1280x720:rate=30 -f lavfi -i sine=frequency=440:sample_rate=48000 -t 3 -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 128k $video
if ($LASTEXITCODE -ne 0) { Fail "failed to create test video" }
& $ffmpeg -y -hide_banner -loglevel error -f lavfi -i testsrc=size=800x600:rate=1 -frames:v 1 $photo
if ($LASTEXITCODE -ne 0) { Fail "failed to create test photo" }

$env:PATH = "$installDir;$oldPath"
$env:ENKI_TEST_ROOT = $testRoot
try {
  $engineTest = @'
import os
from pathlib import Path
from uniquify_engine import uniquify, uniquify_photo

test_root = Path(os.environ["ENKI_TEST_ROOT"])
in_dir = test_root / "input"
out_dir = test_root / "output"
video = in_dir / "sample_video.mp4"
photo = in_dir / "sample_photo.jpg"

uniquify_photo(photo, out_dir / "photos", 1, 1100, "instagram")
for target in (None, 50, 25, 10):
    target_dir = out_dir / ("normal" if target is None else f"compress_{target}")
    uniquify(video, target_dir, 1, 2200 + (target or 0), "instagram", process_audio=True, compression_target_mb=target)
'@
  & .\.venv\Scripts\python.exe -c $engineTest
  if ($LASTEXITCODE -ne 0) { Fail "uniquify engine test failed" }
}
finally {
  $env:PATH = $oldPath
}

$mp4s = Get-ChildItem -Path $outDir -Recurse -Filter "*.mp4"
if ($mp4s.Count -lt 4) { Fail "Expected at least 4 processed MP4 files, got $($mp4s.Count)" }
foreach ($file in $mp4s) {
  $name = $file.Name.ToLowerInvariant()
  if ($name.Contains("unique") -or $name.Contains("uniquified") -or $name.Contains("уникализировано")) {
    Fail "Output file name is not neutral: $($file.Name)"
  }
  & $ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of json $file.FullName | Out-Null
  if ($LASTEXITCODE -ne 0) { Fail "ffprobe failed for $($file.FullName)" }
  & $ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of json $file.FullName | Out-Null
  if ($LASTEXITCODE -ne 0) { Fail "audio stream missing or invalid for $($file.FullName)" }
}

foreach ($target in @(50,25,10)) {
  $compressed = Get-ChildItem -Path (Join-Path $outDir "compress_$target") -Recurse -Filter "*.mp4" | Select-Object -First 1
  if (-not $compressed) { Fail "Missing compressed output for $target MB" }
  $limit = $target * 1024 * 1024
  if ($compressed.Length -gt $limit) { Fail "Compressed output exceeds $target MB: $($compressed.Length)" }
}

$photoOut = Get-ChildItem -Path (Join-Path $outDir "photos") -Recurse -Filter "*.jpg" | Select-Object -First 1
if (-not $photoOut) { Fail "Photo processing output not found" }

$hash = (Get-FileHash -Algorithm SHA256 $setup).Hash.ToLowerInvariant()
Write-Host "EXTENDED_TESTS_SUCCESS"
Write-Host "SETUP=$setup"
Write-Host "SHA256=$hash"
