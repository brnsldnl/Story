# Mimari

## Teknoloji yığını

Tüm bileşenler izin verici açık kaynak lisanslıdır (MIT / BSD / Apache-2.0).
Hiçbir ticari lisans gerekmez.

| Katman | Seçim | Lisans | Neden |
|---|---|---|---|
| Edge agent | Python 3.11+ | PSF | OpenCV ve okuyucu kütüphaneleri burada en olgun |
| Kamera | OpenCV | Apache-2.0 | UVC kameralarla doğrudan çalışır |
| Yerel kuyruk | SQLite | Kamu malı | Sıfır kurulum, tek dosya, dayanıklı |
| Backend | FastAPI | MIT | Otomatik OpenAPI, tip güvenliği, hızlı |
| ORM | SQLAlchemy 2 | MIT | Olgun, ham SQL'e kaçış serbest |
| Veritabanı | PostgreSQL 16 | PostgreSQL Lisansı | Ücretsiz, boyut sınırı yok, JSONB güçlü |
| Fotoğraf deposu | Dosya sistemi | — | Yedek boyutunu kontrol altında tutar |
| Panel | React + TypeScript | MIT | (planlanan) |
| Kurulum | Docker Compose | Apache-2.0 | Yerinde (on-premise) |

### Neden MSSQL değil PostgreSQL?

Logo MSSQL üzerinde çalışıyor ama biz Logo'ya **yazmıyoruz**, yalnızca
okuyoruz. Kendi verimiz için MSSQL kullanmak zorunda değiliz.

MSSQL Express ücretsizdir ancak **10 GB veritabanı sınırı** vardır. Yıllar
içinde biriken kart okuma kayıtlarıyla bu sınıra ulaşmak sürpriz olmaz ve o
noktada lisans satın almanız gerekir. PostgreSQL'de böyle bir duvar yok.

### Neden Python (ve .NET değil)?

İlk düşünce .NET olabilir; Logo ekosistemi .NET+MSSQL dünyasıdır. Ancak:

- Logo'ya yazma **Tiger Objects REST** üzerinden yapılacak. REST, HTTP+JSON
  demektir — COM interop gerektiren Logo Objects'in aksine her dilden
  çağrılabilir. .NET zorunluluğu ortadan kalkıyor.
- Kamera işleme Python'da belirgin biçimde kolay.
- Edge ve backend aynı dilde olunca tek ekip, tek test altyapısı, paylaşılan
  yardımcı kod.

---

## Bileşenler

```
┌──────────────────────────────────────────────────────────────┐
│  SAHA - her kapı bir edge node                                │
│                                                               │
│   Kart okuyucu ──┐                                            │
│                  ├──► Edge Agent (mini PC / Raspberry Pi)     │
│   USB kamera ────┘         │                                  │
│                            ├─ SQLite kuyruk (offline dayanım) │
│                            ├─ heartbeat (sessiz ölüm tespiti) │
│                            └─ NTP saat senkronu               │
└────────────────────────────┼──────────────────────────────────┘
                             │ HTTPS + terminal API anahtarı
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  UYGULAMA SUNUCUSU (kurum içi)                                │
│                                                               │
│   FastAPI  ──►  Puantaj Motoru (saf fonksiyon, DB'den bağımsız)│
│      │                                                        │
│      ├──► Zamanlanmış işler                                   │
│      │     • gecelik puantaj hesabı                           │
│      │     • KVKK fotoğraf imhası                             │
│      │     • Logo personel senkronu                           │
│      │                                                        │
│      ├──► PostgreSQL (PDKS verisi)                            │
│      └──► Dosya deposu (fotoğraflar)                          │
└──────────┬────────────────────────────┬───────────────────────┘
           │                            │
     Web Panel (React)            LOGO TIGER (MSSQL)
     + self-servis portal         ◄── SQL ile OKU (salt okunur)
                                  ──► Tiger Objects REST ile YAZ
```

---

## Çoklu lokasyon ve çoklu okuyucu

Çoklu yapı **sonradan eklenen bir özellik değil, şemanın temeli**:

- `sites` — her lokasyonun kendi saat dilimi var
- `terminals` — her okuyucu bir lokasyona bağlı, kendi API anahtarı var
- `user_site_scopes` / `user_department_scopes` — kimin neyi göreceği

Tek panelde tüm lokasyonlar görünür, ama **kapsam kısıtlamasıyla**: genel müdür
hepsini görür, şube amiri yalnızca kendi şubesini. Bu ayrım olmadan "tek panel"
KVKK açısından savunulamaz.

Yön belirleme (`toggle` modu) lokasyon bazlıdır: bir çalışanın Ankara
şubesindeki hareketi, İstanbul'daki hareketinin yönünü bozmaz.

---

## En kritik tasarım kararı: ham veri / türetilmiş veri ayrımı

```
attendance_events (HAM - asla UPDATE/DELETE edilmez, kanaldan bağımsız)
    +
adjustments       (manuel düzeltmeler, onay zinciriyle, ayrı tabloda)
    +
shifts / leaves / holidays / overtime_approvals
    ↓
    │  puantaj motoru (saf fonksiyon)
    ↓
attendance_days   (TÜRETİLMİŞ - her zaman yeniden hesaplanabilir)
```

Bir yöneticinin "Ahmet dün 18:00'de çıktı, düzelt" talebi **ham kaydı
değiştirmez**; `adjustments` tablosuna gerekçesi ve onaylayanıyla yazılır.
Motor ham veri ile düzeltmeleri birleştirerek sonucu üretir.

Kazandırdıkları:

- **Yeniden hesaplanabilirlik** — Mola kuralı değişti mi? Motoru güncelleyip
  geçmiş dönemi yeniden hesaplayın. Ham veri elinizde duruyor.
- **Denetlenebilirlik** — "Bu rakam neden böyle?" sorusunun cevabı her zaman
  üretilebilir.
- **Güven** — Hiçbir yönetici ham geçiş kaydını sessizce değiştiremez.

Bu kararı baştan vermezseniz altı ay sonra geri dönüşü çok pahalıdır.

---

## Kanal bağımsızlığı

Okutma kaydı hangi yoldan geldiğinden bağımsızdır. `attendance_events` tablosu
üç kanalı birden taşır:

| Kanal | Nasıl | Nerede kullanılır |
|---|---|---|
| `card` | Terminalde kart okutulur, fotoğraf çekilir | Asıl kanal |
| `qr` | Terminal ekranındaki dönen QR telefonla okutulur | Yedek / donanımsız nokta |
| `manual` | Yönetici elle girer (düzeltme akışı) | İstisna |

Puantaj motoru kanalı bilmez; bir hareketin giriş mi çıkış mı olduğuyla
ilgilenir. Bu sayede yeni bir kanal eklemek motoru değiştirmez, ve QR ile
kart aynı gün içinde karışık kullanılabilir (kartını unutan personel o gün
QR ile okutur, puantajı doğru hesaplanır).

Ayrıntı: [04-qr-ve-konum.md](04-qr-ve-konum.md)

---

## Veri kaybetmeme garantisi

Bir kart okuması kaybolursa bir çalışanın günlük puantajı yanlış hesaplanır.
Bu yüzden zincirin her halkası korunur:

1. **Diske önce yaz, sonra gönder.** Edge agent okumayı ve fotoğrafı SQLite'a
   yazar, ancak ondan sonra göndermeyi dener.
2. **SQLite WAL + `synchronous=FULL`.** Elektrik kesintisinde yarım kayıt
   kalmaz.
3. **Artan bekleme ile yeniden deneme.** Ağ koptuğunda 2s, 5s, 15s... 5dk
   aralıklarla denenir; kayıt kuyrukta bekler.
4. **Mükerrer koruması.** Her olayın `client_event_id` (UUID) değeri vardır.
   Sunucu aynı kimliği ikinci kez görürse 409 döner. Bu sayede "gönderdim mi
   acaba" belirsizliğinde tekrar göndermek güvenlidir.
5. **Heartbeat.** Terminal kart okumasa bile dakikada bir hayatta olduğunu
   bildirir. Sessiz veri kaybının tek savunması budur.
6. **Sıra korunur.** Kuyruk en eski okumadan başlayarak boşaltılır; giriş/çıkış
   sırası puantajı belirlediği için bu önemlidir.
7. **Tanınmayan kart da kaydedilir.** Kaydı düşürmek "kartım çalışmıyor"
   şikayetini araştırılamaz hale getirir.
8. **Kamera arızası okumayı düşürmez.** Fotoğrafsız kayıt, kayıt olmamasından
   iyidir.

---

## Logo Tiger entegrasyonu

### Okuma: MSSQL, salt okunur

```
Logo MSSQL  ──(pyodbc, readonly)──►  LogoReader  ──►  employees / departments
```

**Sorgu koda gömülü değildir**, yapılandırmadan gelir
(`app/integrations/logo/queries.example.sql`). Sebebi: Logo tablo isimleri
firma numarası içerir (`LG_001_...`), sürümler arası değişir ve her kurulumda
farklı alanlar kullanılır. Sorguyu dışarı almak, Logo yükseltildiğinde kod
değiştirmeden uyum sağlamayı mümkün kılar.

Eşleştirme `LOGICALREF` üzerinden yapılır, personel kodu üzerinden değil: kod
değişse bile kayıt kaybolmaz.

Logo'da görünmeyen personel **silinmez, pasife çekilir**. Geçmiş puantajın
bağlı olduğu satırı silmek denetim izini yok eder.

### Yazma: yalnızca Tiger Objects REST

Logo tablolarına **doğrudan INSERT/UPDATE yapılmaz.** Bu, Logo desteğini
geçersiz kılar ve veri bütünlüğünü bozar.

Bordro modülü henüz kullanılmadığı için puantaj aktarımı şu an devre dışıdır
(`writer.py`). Kimlik doğrulama ve token yönetimi hazır; bordroya geçildiğinde
yalnızca mesai türü → Logo puantaj kodu eşlemesi tanımlanacak.

Bu eşleme kasıtlı olarak boş bırakılmıştır: **yanlış eşleme yanlış maaş
demektir**, varsayımla doldurulacak bir yer değildir.
