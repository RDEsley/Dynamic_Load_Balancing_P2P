# Mostra IPs IPv4 da maquina (use o da rede local, ex. 192.168.x.x)
Write-Host "`n=== Enderecos IPv4 desta maquina ===" -ForegroundColor Cyan
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' } |
    Select-Object IPAddress, InterfaceAlias |
    Format-Table -AutoSize

Write-Host "Para o projeto, use o IP da rede local (Wi-Fi ou Ethernet), nao 127.0.0.1," -ForegroundColor Yellow
Write-Host "se outro PC na mesma rede for conectar aos Masters.`n"
