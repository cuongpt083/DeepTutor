# Powershell script to build DeepTutor Windows Installer (MSI/NSIS) via Tauri
param(
    [switch]$SkipPythonBundle = $false
)

Write-Host "=== Building DeepTutor Desktop Installer ===" -ForegroundColor Cyan

# Step 1: Bundle Python backend if requested
if (-not $SkipPythonBundle) {
    Write-Host "Step 1: Freezing Python backend..." -ForegroundColor Yellow
    & "$PSScriptRoot\bundle-python.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Python bundle failed. Aborting installer build."
        exit $LASTEXITCODE
    }
}

# Step 2: Run Tauri Build
Write-Host "Step 2: Compiling Tauri Windows executable and installer..." -ForegroundColor Yellow
Push-Location "$PSScriptRoot\..\src-tauri"

try {
    cargo tauri build
    if ($LASTEXITCODE -eq 0) {
        Write-Host "=== Desktop installer build complete! ===" -ForegroundColor Green
        Write-Host "Installers located at: desktop\src-tauri\target\release\bundle\" -ForegroundColor Cyan
    } else {
        Write-Error "Tauri build failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
