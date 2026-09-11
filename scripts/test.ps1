# PDKS - tum testleri calistirir
#
#   powershell -ExecutionPolicy Bypass -File scripts\test.ps1
#
# Parametre olarak pytest secenekleri gecebilirsiniz:
#   ...\test.ps1 -k gece        (yalnizca adinda 'gece' gecen testler)
#   ...\test.ps1 -v             (ayrintili)

param([Parameter(ValueFromRemainingArguments=$true)] $PytestArgs)

$ErrorActionPreference = "Stop"
$ProjeKok = Split-Path -Parent $PSScriptRoot
$py = Join-Path $ProjeKok ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "HATA: Sanal ortam yok. Once scripts\kur.ps1 calistirin." -ForegroundColor Red
    exit 1
}

# Backend testleri veritabani ister
$env:DATABASE_URL = "postgresql+psycopg://pdks:pdks@localhost:5432/pdks"

Write-Host "BACKEND testleri" -ForegroundColor Cyan
Push-Location (Join-Path $ProjeKok "backend")
& $py -m pytest @PytestArgs
$backendSonuc = $LASTEXITCODE
Pop-Location

Write-Host "`nEDGE testleri" -ForegroundColor Cyan
Push-Location (Join-Path $ProjeKok "edge")
& $py -m pytest @PytestArgs
$edgeSonuc = $LASTEXITCODE
Pop-Location

Write-Host ""
if ($backendSonuc -eq 0 -and $edgeSonuc -eq 0) {
    Write-Host "Tum testler gecti." -ForegroundColor Green
    exit 0
} else {
    Write-Host "Basarisiz testler var." -ForegroundColor Red
    exit 1
}
