# PDKS - Windows yerel geliştirme kurulumu
#
#   powershell -ExecutionPolicy Bypass -File scripts\kur.ps1
#
# Yaptıkları: sanal ortam oluşturur, bağımlılıkları kurar, veritabanını
# Docker ile ayağa kaldırır ve şemayı uygular.

$ErrorActionPreference = "Stop"
$ProjeKok = Split-Path -Parent $PSScriptRoot

Write-Host "PDKS yerel kurulum" -ForegroundColor Cyan
Write-Host "Proje dizini: $ProjeKok`n"

# --- Python kontrolü ---
try {
    $pyVersion = (python --version 2>&1)
    Write-Host "[1/5] $pyVersion bulundu" -ForegroundColor Green
} catch {
    Write-Host "HATA: Python bulunamadi. Python 3.11+ kurun: https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "      Kurulumda 'Add Python to PATH' secenegini isaretleyin." -ForegroundColor Yellow
    exit 1
}

# --- Sanal ortam ---
$venv = Join-Path $ProjeKok ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "[2/5] Sanal ortam olusturuluyor..." -ForegroundColor Cyan
    python -m venv $venv
} else {
    Write-Host "[2/5] Sanal ortam zaten var" -ForegroundColor Green
}

$py = Join-Path $venv "Scripts\python.exe"

# --- Bagimliliklar ---
Write-Host "[3/5] Bagimliliklar kuruluyor (birkac dakika surebilir)..." -ForegroundColor Cyan
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -e "$ProjeKok\backend[dev]"
& $py -m pip install --quiet -e "$ProjeKok\edge[dev]"
Write-Host "      Bagimliliklar kuruldu" -ForegroundColor Green

# --- Veritabani ---
Write-Host "[4/5] Veritabani baslatiliyor..." -ForegroundColor Cyan
try {
    docker version --format '{{.Server.Version}}' | Out-Null
} catch {
    Write-Host "HATA: Docker bulunamadi. Docker Desktop kurun:" -ForegroundColor Red
    Write-Host "      https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    Write-Host "      Alternatif: PostgreSQL 16'yi dogrudan kurup db\init\001_init.sql dosyasini uygulayin." -ForegroundColor Yellow
    exit 1
}

Push-Location $ProjeKok
docker compose -f docker-compose.dev.yml up -d
Pop-Location

Write-Host "      Veritabaninin hazir olmasi bekleniyor..." -ForegroundColor Gray
$hazir = $false
foreach ($i in 1..30) {
    Start-Sleep -Seconds 2
    $durum = docker exec pdks-dev-db pg_isready -U pdks -d pdks 2>&1
    if ($LASTEXITCODE -eq 0) { $hazir = $true; break }
}
if (-not $hazir) {
    Write-Host "HATA: Veritabani 60 saniyede hazir olmadi." -ForegroundColor Red
    Write-Host "      Kontrol: docker compose -f docker-compose.dev.yml logs db" -ForegroundColor Yellow
    exit 1
}
Write-Host "      Veritabani hazir (localhost:5432)" -ForegroundColor Green

# --- Dogrulama ---
Write-Host "[5/5] Kurulum dogrulaniyor..." -ForegroundColor Cyan
$tablolar = docker exec pdks-dev-db psql -U pdks -d pdks -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"
Write-Host "      $($tablolar.Trim()) tablo olusturuldu" -ForegroundColor Green

Write-Host "`nKurulum tamam." -ForegroundColor Green
Write-Host "`nSirada:" -ForegroundColor Cyan
Write-Host "  Testleri calistir : powershell -ExecutionPolicy Bypass -File scripts\test.ps1"
Write-Host "  Sunucuyu baslat   : powershell -ExecutionPolicy Bypass -File scripts\calistir.ps1"
