$root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $root "config\env\worker-b.env"
$asyncio = Join-Path $root "AsyncIO"

if (-not (Test-Path $envFile)) {
    & (Join-Path $PSScriptRoot "generate-env.ps1")
}

Copy-Item $envFile (Join-Path $asyncio ".env") -Force
Set-Location $asyncio
Write-Host "=== Worker B1 ===" -ForegroundColor Green
Get-Content .env
Write-Host ""
python worker.py
