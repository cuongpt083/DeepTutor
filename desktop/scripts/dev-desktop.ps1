# Powershell script to run DeepTutor Desktop App in development mode
Write-Host "=== Launching DeepTutor Desktop in Development Mode ===" -ForegroundColor Cyan

Push-Location "$PSScriptRoot\..\src-tauri"
try {
    cargo tauri dev
} finally {
    Pop-Location
}
