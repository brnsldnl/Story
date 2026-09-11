# Yerel Geliştirme (Windows)

Kodu kendi makinenizde tutup testleri yerelde çalıştırmak için.

Örnek dizin: `D:\claude\personel takip`

## Neden yerel gerekiyor

Bu proje bir noktadan sonra **zorunlu olarak** yerelde geliştirilir:

- **Kart okuyucu ve kamera USB cihazlar** — bulut ortamına takılamazlar
- **Logo Tiger SQL sunucunuz iç ağınızda** — dışarıdan erişilemez

Yani bulutta ne kadar test edilirse edilsin, bu iki şey sizin makinenizde
denenmeden sistem bitmiş sayılmaz.

## Gereksinimler

| | Nereden |
|---|---|
| Python 3.11+ | https://www.python.org/downloads/ — kurulumda **"Add Python to PATH"** işaretleyin |
| Docker Desktop | https://www.docker.com/products/docker-desktop/ |
| Git (opsiyonel) | https://git-scm.com/download/win |

Docker istemiyorsanız PostgreSQL 16'yı doğrudan kurup `db\init\001_init.sql`
dosyasını elle uygulayabilirsiniz.

## Kurulum

```powershell
cd "D:\claude\personel takip"
powershell -ExecutionPolicy Bypass -File scripts\kur.ps1
```

Betik sırasıyla: sanal ortam oluşturur, bağımlılıkları kurar, PostgreSQL'i
Docker ile başlatır, şemayı uygular ve tablo sayısını doğrular.

## Testler

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
```

100 test çalışır (93 backend, 7 edge). Belirli testleri süzmek için:

```powershell
scripts\test.ps1 -k gece        # gece vardiyası testleri
scripts\test.ps1 -k qr -v       # QR testleri, ayrıntılı
```

## Sunucuyu çalıştırma

```powershell
powershell -ExecutionPolicy Bypass -File scripts\calistir.ps1
```

API dokümantasyonu: http://127.0.0.1:8000/docs — buradan uçları tarayıcıdan
deneyebilirsiniz.

## Terminal agent'ı donanımsız çalıştırma

```powershell
# edge\config.yaml içinde: reader.type: mock, camera.enabled: false
.venv\Scripts\python.exe -m pdks_edge --config edge\config.yaml
```

Kart okutmak (başka bir pencerede):

```powershell
"04A2B3C4D5" | Out-File -Encoding ascii $env:TEMP\pdks_card
```

## Gerçek Logo Tiger'a bağlanma

Buluttan yapılamayan asıl test budur.

1. Logo veritabanınızda **salt okunur** bir kullanıcı açın:

```sql
CREATE LOGIN pdks_read WITH PASSWORD = '...';
USE LOGODB;
CREATE USER pdks_read FOR LOGIN pdks_read;
ALTER ROLE db_datareader ADD MEMBER pdks_read;
```

> Yazma yetkisi **vermeyin**. Logo'ya yazma yalnızca Tiger Objects REST
> üzerinden yapılır; doğrudan tablo yazımı Logo desteğini geçersiz kılar.

2. Kendi kurulumunuzun tablo adlarını bulun:

```sql
SELECT name FROM sys.tables WHERE name LIKE 'LG_%' ORDER BY name;
```

3. `backend\app\integrations\logo\queries.example.sql` dosyasındaki sorguyu
   kendi tablo ve alan adlarınıza göre düzenleyin.

4. Bağlantıyı `.env` dosyasına yazın:

```
LOGO_SYNC_ENABLED=true
LOGO_MSSQL_DSN=DRIVER={ODBC Driver 18 for SQL Server};SERVER=logo-sunucu;DATABASE=LOGODB;UID=pdks_read;PWD=...;TrustServerCertificate=yes
```

Windows'ta [ODBC Driver for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
kurulu olmalı. Ardından:

```powershell
.venv\Scripts\python.exe -m pip install pyodbc
```

⚠️ `LOGO_MSSQL_DSN` parola içerir — `.env` dosyası `.gitignore`'da, asla
commit edilmemeli.

## Gerçek kart okuyucu ile test

Windows'ta PC/SC yerleşiktir (`winscard`), ek servis gerekmez:

```powershell
.venv\Scripts\python.exe -m pip install pyscard opencv-python
```

`edge\config.yaml`:

```yaml
reader:
  type: pcsc
  reader_index: 0
camera:
  enabled: true
  device_index: 0
```

> `reader.type: hid` seçeneği **Linux'a özeldir** (evdev kullanır), Windows'ta
> çalışmaz. Windows'ta `pcsc` veya `serial` kullanın.

## Platform farkları

Varsayılan dizinler işletim sistemine göre belirlenir
(`backend\app\core\paths.py`, `edge\pdks_edge\paths.py`):

| | Windows | Linux (üretim) |
|---|---|---|
| Fotoğraflar | `C:\ProgramData\PDKS\photos` | `/var/lib/pdks/photos` |
| Terminal kuyruğu | `C:\ProgramData\PDKS-Edge\queue.db` | `/var/lib/pdks-edge/queue.db` |
| QR görseli | `%TEMP%\pdks-qr.png` | `/run/pdks-edge/qr.png` |

Yapılandırmada açık yol verirseniz her zaman o kullanılır.

> Üretim Linux'ta çalışacak. Windows'ta geçen bir testin Linux'ta da geçmesi
> beklenir ama garanti değildir; kritik değişikliklerden sonra Docker ile
> Linux'ta da doğrulayın.

## Veritabanına doğrudan bakma

```powershell
docker exec -it pdks-dev-db psql -U pdks -d pdks

# Örnekler:
# \dt                                    tabloları listele
# SELECT * FROM attendance_events;       okutma kayıtları
# \d attendance_events                   tablo yapısı
```

## Sık karşılaşılanlar

**`kur.ps1 cannot be loaded because running scripts is disabled`**
→ `-ExecutionPolicy Bypass` parametresini kullanın (yukarıdaki komutlarda var).

**`docker: command not found`**
→ Docker Desktop kurulu ve **çalışıyor** olmalı; sistem tepsisinden başlatın.

**`connection refused` (testlerde)**
→ Veritabanı ayakta mı: `docker compose -f docker-compose.dev.yml ps`

**Veritabanını sıfırlama**

```powershell
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d
```

`-v` kalıcı diski de siler; şema yeniden uygulanır. **Tüm veri gider.**

## Bulut ile yerel arasında senkron

```
Bulut (Claude)  ──push──►  GitHub  ──pull──►  D:\claude\personel takip
```

```powershell
git pull origin claude/new-session-4o5a75
```

GitHub kullanmak istemiyorsanız kodu arşiv olarak da alabilirsiniz; ancak o
zaman her güncelleme elle taşınır. Depoyu `private` yapmak çoğu durumda
yeterli olur.
