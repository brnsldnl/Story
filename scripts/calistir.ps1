# PDKS - API sunucusunu yerelde baslatir
#
#   powershell -ExecutionPolicy Bypass -File scripts\calistir.ps1
#
# Kod degisikliklerinde otomatik yeniden yuklenir.
# API dokumantasyonu: http://127.0.0.1:8000/docs

$ErrorActionPreference = "Stop"
$ProjeKok = Split-Path -Parent $PSScriptRoot
$py = Join-Path $ProjeKok ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "HATA: Sanal ortam yok. Once scripts\kur.ps1 calistirin." -ForegroundColor Red
    exit 1
}

# Yerel gelistirme degerleri - URETIMDE KULLANMAYIN
$env:DATABASE_URL = "postgresql+psycopg://pdks:pdks@localhost:5432/pdks"
$env:JWT_SECRET = "yerel-gelistirme-jwt-anahtari-en-az-otuziki-bayt"
$env:QR_MASTER_SECRET = "yerel-gelistirme-qr-ana-anahtari-en-az-otuziki-bayt"
$env:PHOTO_STORAGE_PATH = Join-Path $ProjeKok "data\photos"

New-Item -ItemType Directory -Force -Path $env:PHOTO_STORAGE_PATH | Out-Null

Write-Host "API baslatiliyor: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "Durdurmak icin Ctrl+C`n" -ForegroundColor Gray

Push-Location (Join-Path $ProjeKok "backend")
& $py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
Pop-Location
