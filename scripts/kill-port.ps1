param([int]$Port = 8000)
$lines = netstat -ano | Select-String ":$Port\s"
if (-not $lines) {
    Write-Host "Porta $Port livre." -ForegroundColor Green
    exit 0
}
Write-Host "Processos na porta $Port:" -ForegroundColor Yellow
$pids = $lines | ForEach-Object {
    if ($_ -match '\s+(\d+)\s*$') { $matches[1] }
} | Select-Object -Unique
foreach ($pid in $pids) {
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    Write-Host "  PID $pid - $($proc.ProcessName)"
}
$confirm = Read-Host "Encerrar esses processos? (s/N)"
if ($confirm -eq 's') {
    $pids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Write-Host "Porta $Port liberada." -ForegroundColor Green
}
