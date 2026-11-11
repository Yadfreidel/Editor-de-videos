$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
py -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Instala Python 3.11 o posterior y vuelve a intentar.' }
& .venv/Scripts/python.exe -m pip install -r backend/requirements-optional.txt
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de Python.' }
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de Node.' }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host 'Dependencias listas. Configura .env; consulta README.md para instalar una voz española.'
