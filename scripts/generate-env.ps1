# Gera .env para Master A, Master B e Worker no AsyncIO/
param(
    [string]$Ip = "",
    [int]$PortA = 8000,
    [int]$PortB = 8001
)

if (-not $Ip) {
    $Ip = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
        Select-Object -First 1 -ExpandProperty IPAddress)
}

if (-not $Ip) {
    Write-Host "Nao foi possivel detectar IP. Passe manualmente: .\generate-env.ps1 -Ip 192.168.1.15" -ForegroundColor Red
    exit 1
}

$asyncio = Join-Path $PSScriptRoot "..\AsyncIO"
$envDir = Join-Path $PSScriptRoot "..\config\env"

New-Item -ItemType Directory -Force -Path $envDir | Out-Null

$masterA = @"
# Master A (saturado) - copie para AsyncIO/.env antes de: python master.py
HOST=0.0.0.0
PORT=$PortA
SERVER_UUID=Master_A
MASTER_ID=A
CAPACITY=100
NUM_TASKS=120
NEIGHBOR_MASTERS=B=${Ip}:${PortB}
"@

$masterB = @"
# Master B (vizinho) - copie para AsyncIO/.env antes de: python master.py
HOST=0.0.0.0
PORT=$PortB
SERVER_UUID=Master_B
MASTER_ID=B
CAPACITY=100
NUM_TASKS=0
NEIGHBOR_MASTERS=A=${Ip}:${PortA}
"@

$workerB = @"
# Worker do Master B - copie para AsyncIO/.env antes de: python worker.py
HOST=$Ip
PORT=$PortB
WORKER_UUID=Worker_B1
ORIGINAL_MASTER_ID=B
"@

Set-Content -Path (Join-Path $envDir "master-a.env") -Value $masterA -Encoding UTF8
Set-Content -Path (Join-Path $envDir "master-b.env") -Value $masterB -Encoding UTF8
Set-Content -Path (Join-Path $envDir "worker-b.env") -Value $workerB -Encoding UTF8

Write-Host "`nIP usado: $Ip" -ForegroundColor Green
Write-Host "Arquivos gerados em config/env/:" -ForegroundColor Cyan
Write-Host "  master-a.env  -> Master A porta $PortA (fila grande)"
Write-Host "  master-b.env  -> Master B porta $PortB"
Write-Host "  worker-b.env  -> Worker do B"
Write-Host "`nProximo passo: abra 3 terminais e use os scripts em scripts/run-*.ps1`n"
