$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fail($m) { throw $m }

if (-not (Get-Command py -ErrorAction SilentlyContinue)) { Fail "Python Launcher не найден" }
if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)) { Fail "ffmpeg.exe не найден в PATH" }
if (-not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) { Fail "ffprobe.exe не найден в PATH" }

if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r requirements-build.txt

# Static import/syntax check before packaging.
& .\.venv\Scripts\python.exe -m py_compile app.py uniquify_engine.py

& .\.venv\Scripts\pyinstaller.exe --noconfirm --clean EnkiAgencyUniq.spec
$dist = Join-Path $PSScriptRoot "dist\Enki Agency Uniq"
$exe = Join-Path $dist "Enki Agency Uniq.exe"
if (-not (Test-Path $exe)) { Fail "PyInstaller не создал Enki Agency Uniq.exe" }

Copy-Item (Get-Command ffmpeg.exe).Source (Join-Path $dist "ffmpeg.exe") -Force
Copy-Item (Get-Command ffprobe.exe).Source (Join-Path $dist "ffprobe.exe") -Force

# Verify required runtime files.
$required = @("Enki Agency Uniq.exe","ffmpeg.exe","ffprobe.exe")
foreach ($f in $required) {
  if (-not (Test-Path (Join-Path $dist $f))) { Fail "Отсутствует обязательный файл: $f" }
}

# Launch smoke test: process should start and remain alive for a few seconds.
$p = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 5
if ($p.HasExited) { Fail "Приложение завершилось сразу после запуска. ExitCode=$($p.ExitCode)" }
Stop-Process -Id $p.Id -Force

# Build one-click Setup.exe.
$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
  $candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
  if (Test-Path $candidate) { $iscc = Get-Item $candidate } else { Fail "Inno Setup 6 не найден" }
}
& $iscc.Source installer.iss

$setup = Join-Path $PSScriptRoot "installer\Enki_Agency_Uniq_2.5.1_Setup.exe"
if (-not (Test-Path $setup)) { Fail "Setup.exe не создан" }

# Silent install smoke test into the current user profile.
$proc = Start-Process -FilePath $setup -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -PassThru -Wait
if ($proc.ExitCode -ne 0) { Fail "Тестовая установка завершилась с кодом $($proc.ExitCode)" }

$installed = Join-Path $env:LOCALAPPDATA "Programs\Enki Agency Uniq\Enki Agency Uniq.exe"
if (-not (Test-Path $installed)) { Fail "После установки приложение не найдено" }

$p2 = Start-Process -FilePath $installed -PassThru
Start-Sleep -Seconds 5
if ($p2.HasExited) { Fail "Установленная версия завершилась сразу после запуска" }
Stop-Process -Id $p2.Id -Force

$hash=(Get-FileHash -Algorithm SHA256 $setup).Hash.ToLower()
Write-Host "SUCCESS"
Write-Host "SETUP=$setup"
Write-Host "SHA256=$hash"
