# Build the installable app:
#   powershell -ExecutionPolicy Bypass -File touff\packaging\build.ps1
#
# Output in touff\packaging\dist:
#   Touff\                          the app folder (Touff.exe + touff-cli.exe)
#   Touff-<version>-portable.zip    the same folder zipped
#   Touff-Setup-<version>.exe       the installer, if Inno Setup 6 is installed
#
# Needs the dev environment with the build extra (uv pip install -e ".[dev,build]")
# and uv on PATH (uv.exe is shipped inside the app to install the voice pack).
param(
    [string]$Python = "",
    [switch]$RequireInstaller  # fail instead of skipping when Inno Setup is missing (CI)
)
$ErrorActionPreference = "Stop"

$here = $PSScriptRoot
$app = Split-Path $here -Parent
if (-not $Python) { $Python = Join-Path $app ".venv\Scripts\python.exe" }
$dist = Join-Path $here "dist"
$work = Join-Path $here "build"
$version = ([regex]'__version__ = "([^"]+)"').Match((Get-Content (Join-Path $app "touff\__init__.py") -Raw)).Groups[1].Value
Write-Host "Building Touff $version" -ForegroundColor Magenta

Write-Host "1/4 Icon" -ForegroundColor Magenta
& $Python (Join-Path $here "make_icon.py") (Join-Path $work "touff.ico")
if ($LASTEXITCODE) { throw "icon failed" }

Write-Host "2/4 PyInstaller" -ForegroundColor Magenta
if (-not $env:TOUFF_UV) { $env:TOUFF_UV = (Get-Command uv -ErrorAction Stop).Source }
& $Python -m PyInstaller (Join-Path $here "touff.spec") --noconfirm --clean --distpath $dist --workpath $work
if ($LASTEXITCODE) { throw "PyInstaller failed" }
$folder = Join-Path $dist "Touff"
$mb = [math]::Round(((Get-ChildItem $folder -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "   $folder ($mb MB)"

Write-Host "3/4 Portable zip" -ForegroundColor Magenta
$zip = Join-Path $dist "Touff-$version-portable.zip"
& $Python -c "import shutil, sys; shutil.make_archive(sys.argv[1][:-4], 'zip', sys.argv[2], 'Touff')" $zip $dist
if ($LASTEXITCODE) { throw "zip failed" }
Write-Host ("   $zip ({0} MB)" -f [math]::Round((Get-Item $zip).Length / 1MB, 1))

Write-Host "4/4 Installer" -ForegroundColor Magenta
$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source }
if ($iscc) {
    & $iscc "/DAppVersion=$version" "/DAppDir=$folder" "/DOutputDir=$dist" "/DIconFile=$(Join-Path $work 'touff.ico')" (Join-Path $here "installer.iss")
    if ($LASTEXITCODE) { throw "Inno Setup failed" }
    $setup = Join-Path $dist "Touff-Setup-$version.exe"
    Write-Host ("   $setup ({0} MB)" -f [math]::Round((Get-Item $setup).Length / 1MB, 1))
} elseif ($RequireInstaller) {
    throw "Inno Setup 6 (ISCC.exe) not found"
} else {
    Write-Host "   Inno Setup 6 not found: skipped the installer, use the portable zip (https://jrsoftware.org/isinfo.php)" -ForegroundColor DarkYellow
}
Write-Host "`nDone." -ForegroundColor Green
