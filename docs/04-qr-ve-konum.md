# QR Kod ve Konum Doğrulama

Kart okutmanın yanında ikinci bir kanal: çalışan telefonuyla terminal
ekranındaki QR kodu okutur, sistem konumu da doğrular.

Piyasadaki bulut tabanlı PDKS ürünlerinin (Kolay İK, Patron PDKS, QR-PDKS ve
benzerleri) temel satış argümanı budur: **donanım almadan personel takibi**.

## Bu kanal size ne katıyor?

Tüm personeliniz sabit lokasyonda çalıştığı için QR **asıl kanal değil**.
Yine de üç gerçek faydası var:

1. **Yedek kanal.** Kart okuyucu arızalandığında veya bir personel kartını
   evde unuttuğunda kapıda kalınmaz. Bugün bu durumda tek çare manuel
   düzeltme — yani amirin sonradan elle giriş yapması.
2. **Ucuz nokta açma.** 3-5 kişilik bir şubeye mini PC + okuyucu + kamera
   kurmak kişi başına pahalıdır. Oraya bir tablet koyup QR göstermek yeterli.
3. **Geçiş dönemi.** Donanım tedarik edilene kadar sistem QR ile çalışmaya
   başlayabilir.

## Neden sabit QR kod olmaz

Kapıya asılan sabit bir QR kod **hiçbir şey doğrulamaz**. Bir kez fotoğrafını
çeken kişi onu arkadaşına gönderir, o da evinden okutur.

"Ama konum doğrulaması var" cevabı yeterli değil: mobil cihazlarda sahte konum
üretmek (mock location) zor değildir. **Sabit QR + GPS, sanıldığı kadar güçlü
bir kombinasyon değildir.**

## Çözüm: dönen QR

QR kod terminal ekranında gösterilir ve **30 saniyede bir değişir**.

İçeriği şudur:

```
TERMINAL-KODU . zaman-dilimi . HMAC-SHA256-imza
```

Fotoğrafı çekilen kod bir dakika içinde geçersiz olur. Okutma yapabilmek için
kişinin **o anda ekranın karşısında olması** gerekir. Asıl güvence budur.

### Savunma katmanları

| # | Katman | Neyi kanıtlar | Ne kadar güçlü |
|---|---|---|---|
| 1 | Oturum (JWT) | Kim olduğunu | Parola kadar |
| 2 | **Dönen QR** | **Orada olduğunu** | **Asıl güvence** |
| 3 | Cihaz bağı | Hesap ele geçse bile korur | Güçlü |
| 4 | Konum / çit | Destekleyici kanıt | Zayıf, tek başına yetersiz |

Sıralama önemli: **dönen QR olmadan konum doğrulaması güvenlik tiyatrosudur.**

### Anahtar yönetimi

Terminal QR anahtarı **veritabanında saklanmaz**; sunucudaki ana anahtardan
türetilir:

```
terminal_anahtarı = HMAC(QR_MASTER_SECRET, "qr:" + terminal_kodu)
```

Veritabanı sızsa bile geçerli QR üretilemez. Anahtar kuruluma bir kez
terminale verilir; terminal sonrasında kodu **çevrimdışıyken de** üretir —
internet kopsa bile QR ekranda dönmeye devam eder.

## Konum (coğrafi çit)

Her lokasyonun merkez koordinatı ve yarıçapı vardır (varsayılan 150 m).
Kampüste birbirinden uzak kapılar varsa terminal kendi çitini tanımlayabilir.

### Çit dışı okutmaya ne olur

Üç politika var (`sites.geofence_enforcement`):

| Politika | Davranış |
|---|---|
| `flag` (varsayılan) | Kaydedilir, işaretlenir, amir onayına düşer |
| `reject` | Reddedilir, kayıt oluşmaz |
| `off` | Konum hiç kontrol edilmez |

**Varsayılanın `flag` olması bilinçlidir.** GPS kapalı alanda sapar, betonarme
binada doğruluk ciddi biçimde düşer. Kaydı düşürmek çalışanı mağdur eder ve
sorunu araştırılamaz yapar. İşaretlemek hem daha adil hem daha bilgilendirici.

### İki ayrıntı

**Hata payı çalışanın lehine sayılır.** Cihaz "buradayım ama 100 m hata payım
var" diyorsa, çitin 200 m dışında görünen biri içeride kabul edilir. Sınırda
duran kişiyi haksız yere dışarıda göstermemek için.

**Doğruluğu 200 m'den kötü konumla karar verilmez.** Böyle bir konum `unknown`
sayılır. Yanlış olduğunu bilmediğiniz bir veriyle karar vermek, karar
vermemekten daha kötüdür.

### Sahte konum

Cihaz sahte konum sağlayıcı bildirirse kayıt **düşürülmez ama işaretlenir**.
Tek seferlik bir geliştirici ayarı olabilir; tekrarlıyorsa incelenmesi gerekir.
Kaydı reddetmek, sorunu görünmez yapardı.

## KVKK açısından konum

⚠️ **Sürekli konum takibi yapılmıyor ve yapılamaz.**

Konum **yalnızca okutma anında** alınır ve o tek ana ait olarak kaydedilir.
`attendance_events` tablosunda her satır tekil bir andır; bir iz oluşturmaz.
Şema arka plan takibine izin vermez.

Bu önemli bir ayrımdır: çalışanın mesai boyunca konumunu izlemek KVKK
açısından çok daha ağır bir müdahaledir ve ölçülülük ilkesini zorlar. Giriş
anında konum teyidi ise devam kontrolünün doğal parçasıdır.

Mobil uygulama geliştirilirken:
- Konum izni **"yalnızca uygulama kullanılırken"** istenmeli, "her zaman" değil
- Arka plan konum izni **talep edilmemeli**
- Aydınlatma metninde konum verisinin yalnızca okutma anında alındığı
  açıkça belirtilmeli

## Yapılandırma

Terminal tarafı (`edge/config.example.yaml`):

```yaml
qr:
  enabled: true
  secret: "kurulumda-sunucudan-alinan-anahtar"
  period_seconds: 30
  png_path: "/run/pdks-edge/qr.png"
```

Sunucu tarafı (`.env`):

```bash
QR_MASTER_SECRET=            # en az 32 bayt: openssl rand -base64 48
QR_REQUIRE_REGISTERED_DEVICE=true
```

Lokasyon çiti (veritabanı):

```sql
UPDATE sites
SET latitude = 41.0821, longitude = 29.0100,
    geofence_radius_m = 150, geofence_enforcement = 'flag'
WHERE code = 'MERKEZ';
```

## Durum

| | |
|---|---|
| Dönen QR üretimi ve doğrulaması | ✅ Tamam |
| Coğrafi çit kontrolü | ✅ Tamam |
| Cihaz bağlama | ✅ Tamam |
| Okutma API'si (`POST /api/v1/punch/qr`) | ✅ Tamam |
| Terminal tarafı QR üretimi (çevrimdışı) | ✅ Tamam |
| Mobil uygulama | 🔲 Yazılmadı |
| Cihaz kayıt/iptal ekranı | 🔲 Yazılmadı |

Mobil uygulama ayrı bir iştir. Sunucu tarafı hazır: bir React Native veya
Flutter istemcisi `/api/v1/auth/login` ile oturum açıp `/api/v1/punch/qr`
çağırarak çalışır.

---

**Kaynaklar** — piyasadaki benzer ürünler:
[Kolay İK PDKS](https://kolayik.com/pdks) ·
[Patron PDKS – QR ve konum doğrulama](https://www.patronpdks.com/blog/qr-kod-ve-konum-dogrulamayla-guvenli-giris-cikis-cozumu) ·
[QR-PDKS](https://www.qr-pdks.com.tr/) ·
[Polimek QR kodlu PDKS](https://www.polimek.com.tr/yazilim/qr-kodlu-mobil-personel-devam-kontrol-yazilimi/)
