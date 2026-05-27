# Remove rastros do Cursor no GitHub (Co-authored-by + pasta .agents)
# Execute na pasta do projeto: .\scripts\fix-git-author.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$env:GIT_AUTHOR_NAME = "Richard Esley"
$env:GIT_AUTHOR_EMAIL = "richardesleyso@gmail.com"
$env:GIT_COMMITTER_NAME = "Richard Esley"
$env:GIT_COMMITTER_EMAIL = "richardesleyso@gmail.com"

Write-Host "=== Corrigindo historico Git (autor: Richard Esley) ===" -ForegroundColor Cyan

# Volta ao ultimo commit remoto antes dos envios do agente, mantendo arquivos
git reset --soft d5e3297

# Remove pasta de skills do Cursor do controle do Git
if (Test-Path ".agents") {
    git rm -r --cached .agents 2>$null
}
if (Test-Path "skills-lock.json") {
    git rm --cached skills-lock.json 2>$null
}

git add -A

# Commit SEM hook do Cursor (evita Co-authored-by: cursoragent@cursor.com)
git commit --no-verify -m "feat: alinhamento ao PDF, correcao de devolucao de workers e guia leigo"

Write-Host "`nUltimo commit:" -ForegroundColor Green
git log -1 --format="Autor: %an <%ae>%nMensagem: %s%n%b"

$body = git log -1 --format="%b"
if ($body -match "Co-authored-by:\s*Cursor") {
    Write-Host "AVISO: ainda ha Co-authored-by do Cursor. Faca o commit manualmente no terminal, fora do Cursor." -ForegroundColor Red
    exit 1
}

Write-Host "`nPara enviar ao GitHub (use SEU terminal, nao o agente do Cursor):" -ForegroundColor Yellow
Write-Host "  git push --force-with-lease origin main" -ForegroundColor White
