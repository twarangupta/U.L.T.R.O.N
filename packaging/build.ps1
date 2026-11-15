<#
 Clean build of ULTRON into dist\ULTRON\, then the smoke tests on the built exe.

   powershell -File packaging\build.ps1 [-Python <path to python.exe>]

 Needs PyInstaller (pip install -e ".[build]"). Uses no microphone, speaker or model.
 Steps: clean, PyInstaller, copy config\ next to the exe, --self-test, --import-check, report sizes.
#>
param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$timer = [Diagnostics.Stopwatch]::StartNew()

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $Python -m PyInstaller packaging\ultron.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$buildSeconds = [int]$timer.Elapsed.TotalSeconds

# paths.py finds config\ at <folder of the program>\config; PyInstaller 6 puts data in _internal\.
# (Goes away when paths.py moves to %APPDATA%, see BUILD_LOG D38.)
$exeDir = Join-Path $root "dist\ULTRON"
if (-not (Test-Path (Join-Path $exeDir "config"))) {
    Copy-Item -Recurse (Join-Path $root "config") (Join-Path $exeDir "config")
}

$exe = Join-Path $exeDir "ULTRON.exe"
& $exe --self-test
if ($LASTEXITCODE -ne 0) { throw "exe --self-test failed" }
& $exe --import-check
if ($LASTEXITCODE -ne 0) { throw "exe --import-check failed" }

$files = Get-ChildItem $exeDir -Recurse -File
$totalMb = [math]::Round(($files | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "`nBuild time: $buildSeconds s. Folder: $totalMb MB, $($files.Count) files."
Write-Host "Largest files:"
$files | Sort-Object Length -Descending | Select-Object -First 12 |
    ForEach-Object { "{0,8:N1} MB  {1}" -f ($_.Length / 1MB), $_.FullName.Substring($exeDir.Length + 1) }
