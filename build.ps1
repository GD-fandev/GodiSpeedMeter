$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install requirements.txt and PyInstaller first. See README.md.' }
& $pythonPath -m PyInstaller --noconfirm --clean GodiSpeedMeter.spec
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed' }
