# PDKS — Personel Devam Kontrol Sistemi

Kart okuyucu ve kameraya bağlı, çoklu lokasyon destekli personel giriş/çıkış
takip sistemi. Logo Tiger ile entegre çalışır.

Tüm bileşenler açık kaynaktır; ticari lisans gerektirmez.

## Ne yapar

- Kart okutulduğunda giriş/çıkış kaydı ve fotoğraf çeker
- Alternatif olarak dönen QR kod + konum doğrulaması ile mobilden okutma
- Çalışılan süreyi, geç kalmayı, erken çıkışı ve mesaiyi hesaplar
- Gece vardiyası, mola, resmi tatil ve izinleri modeller
- Onaylı / onaysız mesai ayrımı yapar
- Çoklu lokasyon ve çoklu okuyucuyu tek panelde toplar
- KVKK gereklerini şema ve kod seviyesinde karşılar
- Logo Tiger'dan personel okur (SQL), puantajı Tiger Objects REST ile yazar

## Proje yapısı

```
backend/        FastAPI sunucu, puantaj motoru, Logo entegrasyonu
edge/           Terminal agent: kart okuyucu + kamera + offline kuyruk
db/init/        PostgreSQL şeması
docs/           Mimari, donanım ve KVKK dokümanları
panel/          Web panel (planlanan)
```

## Dokümanlar

| | |
|---|---|
| [docs/01-mimari.md](docs/01-mimari.md) | Teknoloji yığını, veri akışı, Logo entegrasyonu |
| [docs/02-donanim.md](docs/02-donanim.md) | **Hangi donanım alınmalı**, kurulum adımları |
| [docs/03-kvkk.md](docs/03-kvkk.md) | KVKK maddelerinin kod karşılıkları |
| [docs/04-qr-ve-konum.md](docs/04-qr-ve-konum.md) | **QR kod + konum doğrulama** ikinci kanalı |
| [docs/05-yerel-gelistirme.md](docs/05-yerel-gelistirme.md) | **Windows'ta yerel kurulum**, gerçek Logo ve kart okuyucu testi |

## Hızlı başlangıç

**Windows'ta yerel geliştirme** (ayrıntı: [docs/05-yerel-gelistirme.md](docs/05-yerel-gelistirme.md)):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\kur.ps1    # kurulum
powershell -ExecutionPolicy Bypass -File scripts\test.ps1   # 100 test
powershell -ExecutionPolicy Bypass -File scripts\calistir.ps1
```

**Linux / üretim:**

```bash
cp .env.example .env
# .env içindeki POSTGRES_PASSWORD, JWT_SECRET ve QR_MASTER_SECRET değerlerini doldurun
docker compose up -d
curl http://localhost:8000/health
```

API dokümantasyonu: http://localhost:8000/docs

### Donanımsız geliştirme

Terminal donanımı gelmeden tüm akış çalıştırılabilir:

```bash
cd edge
pip install -e ".[dev]"
# config.yaml içinde reader.type: mock, camera.enabled: false
python -m pdks_edge --config config.yaml

echo 04A2B3C4D5 > /tmp/pdks_card   # kart okutmakla aynı etki
```

## Testler

```bash
# Backend (PostgreSQL gerektirir)
cd backend && pip install -e ".[dev]"
DATABASE_URL="postgresql+psycopg://pdks:pdks@localhost:5432/pdks" pytest

# Edge
cd edge && pip install -e ".[dev]" && pytest
```

Puantaj motoru veritabanından bağımsızdır; iş kuralları
`backend/tests/test_attendance_engine.py` içinde yazılıdır. Mevzuat veya
şirket politikası değiştiğinde önce oradaki beklentiler değişmelidir.

## Durum

| Bileşen | Durum |
|---|---|
| Veritabanı şeması | ✅ Tamam |
| Edge agent (okuyucu + kamera + offline kuyruk) | ✅ Tamam |
| Veri alım API'si (mükerrer korumalı) | ✅ Tamam |
| Dönen QR + konum doğrulama + cihaz bağlama | ✅ Tamam |
| Oturum açma ve JWT | ✅ Tamam |
| Puantaj motoru (vardiya, gece, mesai, mola) | ✅ Tamam |
| KVKK fotoğraf imha işi | ✅ Tamam |
| Logo personel okuma (SQL) | ✅ Tamam |
| Logo puantaj yazma (Tiger Objects REST) | ⏸️ Bordro kullanılmadığı için beklemede |
| Mobil uygulama (QR okutma istemcisi) | 🔲 Sonraki adım |
| Rol bazlı yetki kapsamı (kapsam filtreleri) | 🔲 Sonraki adım |
| Web panel | 🔲 Sonraki adım |
| Raporlar ve Excel aktarımı | 🔲 Sonraki adım |
| İzin ve vardiya yönetimi ekranları | 🔲 Sonraki adım |
