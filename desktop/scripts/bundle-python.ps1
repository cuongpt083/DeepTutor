# Powershell script to bundle DeepTutor backend with PyInstaller for Desktop App
param(
    [string]$OutputDir = "$PSScriptRoot\..\..\dist\deeptutor-backend"
)

Write-Host "=== Bundling DeepTutor Python Backend ===" -ForegroundColor Cyan

$PythonExe = "$PSScriptRoot\..\..\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

Write-Host "Using Python: $PythonExe"

# Ensure PyInstaller is installed
& $PythonExe -m pip install --upgrade pyinstaller

# Run PyInstaller one-folder bundle
Write-Host "Running PyInstaller..." -ForegroundColor Yellow

& $PythonExe -m PyInstaller `
    --noconfirm `
    --name deeptutor-backend `
    --distpath "$OutputDir\.." `
    --workpath "$OutputDir\..\build" `
    --add-data "$PSScriptRoot\..\..\deeptutor;deeptutor" `
    --hidden-import vieneu `
    --hidden-import onnxruntime `
    --hidden-import uvicorn `
    --hidden-import fastapi `
    --hidden-import aiohttp `
    --hidden-import numpy `
    --collect-data vieneu `
    --collect-all deeptutor `
    "$PSScriptRoot\..\..\deeptutor\__main__.py"

if ($LASTEXITCODE -eq 0) {
    Write-Host "=== Successfully bundled backend to $OutputDir ===" -ForegroundColor Green
} else {
    Write-Error "PyInstaller bundle failed with exit code $LASTEXITCODE"
}
