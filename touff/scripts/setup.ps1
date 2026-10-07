# One-time setup for Touff. Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File touff\scripts\setup.ps1            # lightweight voice only
#   powershell -ExecutionPolicy Bypass -File touff\scripts\setup.ps1 -Expressive # + GPU voice (~3 GB, NVIDIA)
#
# Needs uv (https://docs.astral.sh/uv/). Python is installed *inside* the project
# folder (.python) so nothing depends on AppData, which some launchers redirect.
param([switch]$Expressive)
$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$env:UV_PYTHON_INSTALL_DIR = Join-Path $root ".python"

Write-Host "1/4 Python 3.12 (portable, in .python)" -ForegroundColor Magenta
uv python install 3.12
$py = Get-ChildItem (Join-Path $root ".python") -Filter python.exe -Recurse |
    Where-Object { $_.FullName -match "cpython-3\.12" } | Select-Object -First 1 -ExpandProperty FullName

Write-Host "2/4 App environment (.venv)" -ForegroundColor Magenta
uv venv .venv --python $py --allow-existing
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"

if ($Expressive) {
    Write-Host "3/4 Expressive GPU voice (.venv-voice, ~3 GB)" -ForegroundColor Magenta
    uv venv .venv-voice --python $py --allow-existing
    uv pip install --python .venv-voice\Scripts\python.exe torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
    uv pip install --python .venv-voice\Scripts\python.exe chatterbox-tts faster-whisper
} else {
    Write-Host "3/4 Skipping expressive voice (add -Expressive to install it)" -ForegroundColor DarkGray
}

Write-Host "4/4 Speech models (~270 MB)" -ForegroundColor Magenta
.venv\Scripts\python.exe -m touff --download

Write-Host "`nDone! Double-click Touff.cmd to start her." -ForegroundColor Green
Write-Host "For the big brain, run 'claude' once in a terminal and log in." -ForegroundColor Green
