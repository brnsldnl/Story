# KVKK Uyumu — Teknik Karşılıklar

> Bu doküman teknik tasarımı yönlendirmek içindir, hukuki görüş değildir.
> Aydınlatma metni, açık rıza formu ve VERBİS kaydı gibi konuları KVKK
> danışmanınıza onaylatın.

Buradaki maddelerin hepsinin **kodda ve veritabanında karşılığı vardır**.
"Politika yazdık" demek yetmez; denetimde sorulan şey sistemin ne yaptığıdır.

## 1. Fotoğraf evet, yüz tanıma hayır

| | KVKK durumu |
|---|---|
| Fotoğraf çek, sakla, **yalnızca uyuşmazlıkta** insan gözüyle bak | Normal kişisel veri |
| Yüz tanıma / yüz şablonu çıkar | **Özel nitelikli kişisel veri** (m.6) — açık rıza şart |

Bu proje **yüz tanıma yapmaz** ve yapmamalıdır. Kazancı marjinal, hukuki yükü
ağırdır. Fotoğraf + rastgele denetim yeterli caydırıcılığı sağlar.

Bu yüzden dahili kameralı erişim terminalleri yerine ayrı UVC kamera
kullanıyoruz — bkz. [02-donanim.md](02-donanim.md).

## 2. Saklama süresi ve gerçek imha

`photos.purge_after` — her fotoğrafın imha tarihi **kaydın kendisinde taşınır**,
sonradan hatırlanması gereken bir politika değildir.

`app/services/retention.py` — zamanlanmış iş süresi dolan fotoğrafları
**diskten gerçekten siler**. Veritabanında bayrak çevirmek imha değildir.

Varsayılan: 60 gün (`PHOTO_RETENTION_DAYS`). Kimlik teyidi için bu süre
fazlasıyla yeterlidir.

**Puantaj kayıtları bu işin kapsamı dışındadır.** Onların saklama süresi yasal
zorunluluklara tabidir ve çok daha uzundur. Fotoğraf silinse de giriş/çıkış
kaydı yerinde kalır — bu kasıtlıdır.

Testler: `backend/tests/test_retention.py` — dosyanın gerçekten silindiğini
doğrular.

## 3. Erişim logu

`photo_access_log` — bir fotoğrafa kim, ne zaman, hangi gerekçeyle baktı.
Denetimde ilk sorulan şey budur.

## 4. Veri minimizasyonu

- Fotoğraf 640x480, JPEG kalite 75 — kimlik teyidi için yeterli
- Video yok, ses yok, sürekli kayıt yok
- Kamera boşta açık tutulmaz (`keep_open: false`); yalnızca kart okunduğunda açılır
- Başarılı gönderimden sonra terminaldeki kopya **silinir** — fotoğraf yalnızca
  tek yerde durur

## 5. Rol bazlı erişim

| Rol | Görebildiği |
|---|---|
| `admin` | Her şey |
| `hr` | Tüm personel + fotoğraf |
| `manager` | Yalnızca kapsamındaki lokasyon/departman, **fotoğraf yok** |
| `employee` | Yalnızca kendi kayıtları (self-servis portal) |

Kapsam `user_site_scopes` ve `user_department_scopes` ile sınırlanır. Çoklu
lokasyonda "tek panel" ancak bu kısıtlamayla savunulabilir.

## 6. Şifreleme

- **Aktarımda:** HTTPS zorunlu. Kurum içi CA kullanılıyorsa edge agent
  `verify_tls` ile sertifika yolunu alır — TLS doğrulaması asla kapatılmaz.
- **Diskte:** Sunucu diskinde şifreleme (LUKS) veya PostgreSQL TDE önerilir.

## 7. Terminal kimlik doğrulama

Terminal API anahtarları veritabanında **hash'li** tutulur ve karşılaştırma
sabit zamanlı yapılır (`hmac.compare_digest`). Veritabanı sızsa bile anahtarlar
kullanılamaz olmalıdır.

## 8. Denetim izi

`audit_log` — her manuel müdahale: kim, ne zaman, eski değer, yeni değer,
gerekçe.

Ham geçiş kayıtları (`card_reads`) hiç değiştirilmez; düzeltmeler
`adjustments` tablosunda onay zinciriyle yaşar. Hiçbir yönetici bir geçiş
kaydını sessizce değiştiremez.

## 9. Yurt dışına aktarım yok

Tüm yığın **yerinde (on-premise)** çalışır. Bulut servisi, harici API, yurt
dışı bağımlılığı yoktur.

## 10. Şeffaflık

Self-servis portal (planlanan): çalışan kendi giriş/çıkış kayıtlarını ve izin
bakiyesini görür. Hem KVKK şeffaflık ilkesine hizmet eder hem de İK'ya gelen
"benim saatim yanlış" trafiğinin büyük kısmını keser.

---

## Yazılım dışı adımlar

Bunların kodda karşılığı yok, ama unutulmasın:

- [ ] Aydınlatma metni hazırlanması ve çalışanlara tebliği
- [ ] VERBİS kaydı
- [ ] Kişisel Veri Saklama ve İmha Politikası (yazılı doküman)
- [ ] İlgili kişi başvuru sürecinin tanımlanması
- [ ] Kamera konumuna bilgilendirme levhası
