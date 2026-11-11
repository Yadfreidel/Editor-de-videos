$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv/Scripts/python.exe')) { throw 'Primero instala las dependencias siguiendo README.md.' }
$backendProcess = Start-Process -FilePath (Resolve-Path '.venv/Scripts/python.exe') -ArgumentList '-m uvicorn backend.main:app --host 127.0.0.1 --port 8000' -WindowStyle Hidden -PassThru
try { & npm.cmd run dev } finally { if (-not $backendProcess.HasExited) { Stop-Process -Id $backendProcess.Id } }
