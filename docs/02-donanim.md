# Donanım Seçimi

## Temel karar: okuyucu ile kamerayı ayırın

Tek cümlelik öneri: **hepsi bir arada erişim terminali almayın.** Bunun yerine
bir mini PC'ye ayrı bir kart okuyucu ve ayrı bir USB kamera bağlayın.

Gerekçe:

| | Hepsi bir arada terminal | Mini PC + ayrı okuyucu + kamera |
|---|---|---|
| Kamera erişimi | Üreticinin SDK'sı arkasında, çoğu Windows DLL | Standart UVC, OpenCV ile doğrudan |
| Lisans | SDK çoğu zaman lisanslı/kapalı | Tamamen açık kaynak |
| Yüz tanıma | Genelde zorunlu/varsayılan açık | Kullanmıyoruz (KVKK avantajı) |
| Marka bağımlılığı | Yüksek - model biterse kod değişir | Yok - adapter değiştirilir |
| Offline dayanıklılık | Cihazın insafına kalmış | Bizim kontrolümüzde |
| Kolay kodlama | SDK öğrenme eğrisi | `cv2.VideoCapture(0)` |

Dahili kameralı erişim terminallerinin kamerası neredeyse her zaman **yüz
tanımaya** bağlıdır. Yüz şablonu KVKK m.6 anlamında **özel nitelikli kişisel
veridir** ve açık rıza gerektirir, rıza vermeyene alternatif sunmak
zorundasınız. Ayrı kamera kullanınca yalnızca "fotoğraf" işliyoruz; biyometrik
şablon üretmiyoruz. Hukuki yük belirgin biçimde hafifliyor.

---

## Önerilen terminal seti (kapı başına)

| Bileşen | Öneri | Not |
|---|---|---|
| Bilgisayar | Intel N100 fanless mini PC **veya** Raspberry Pi 5 (4GB) | Fansız olması tozlu fabrika ortamında önemli |
| Kart okuyucu | **PC/SC uyumlu 13.56 MHz NFC okuyucu** (ACR122U ve muadilleri) | Standart sürücü, SDK yok |
| Kamera | Herhangi bir **UVC** USB web kamerası (Logitech C270 sınıfı yeterli) | 640x480 kimlik teyidi için fazlasıyla yeterli |
| Ekran (opsiyonel) | 7" dokunmatik | "Hoş geldin Ayşe - giriş 08:42" geri bildirimi |
| Kesintisiz güç | Küçük UPS | Elektrik kesintisinde kuyruk zaten korunur, ama kapıda kalma olmasın |

Fiyatlar hızla değiştiği için burada tutar yazmıyoruz; tedarik anında teyit
edin. Sıralama olarak mini PC en pahalı, okuyucu ve kamera görece ucuz kalemdir.

### Neden PC/SC?

PC/SC, akıllı kart okuyucuları için **üreticiden bağımsız bir standarttır**.
Linux'ta `pcscd` + `libccid` ile çalışır; kapalı kaynak bir SDK gerekmez.

En önemlisi: bugün aldığınız okuyucu üretimden kalkarsa, aynı standardı
konuşan başka bir marka takılır ve **kodda tek satır değişmez**.

### Alternatif: USB HID "klavye taklidi" okuyucu

En ucuz ve en hızlı başlangıç yolu. Okuyucu kendini USB klavye olarak tanıtır,
kart okunduğunda numarayı "yazar". Sürücü yok, SDK yok, lisans yok.
Türkiye'de her elektronik satıcısında bulunur.

Dezavantajı: marka/model garantisi yok, kart teknolojisi çoğu zaman
belirtilmez. Pilot kurulum ve geliştirme için mükemmel, uzun vadede PC/SC'ye
geçmenizi öneririm.

Bu seçenek de desteklenir (`reader.type: hid`), üstelik tuş vuruşlarını
`EVIOCGRAB` ile özel olarak yakalarız — kart numarası sistemde açık olan başka
bir pencereye sızmaz.

---

## Kart teknolojisi: 125 kHz değil, 13.56 MHz

**125 kHz EM4100 kartlardan uzak durun.** Piyasadan kolayca temin edilen ucuz
bir kopyalama cihazıyla dakikalar içinde çoğaltılabiliyorlar. Puantaja ve
dolayısıyla maaşa etki eden bir sistemde bu gerçek bir risktir.

**13.56 MHz MIFARE (ISO 14443-A)** kullanın.

Dürüst olmak gerekirse: basit bir okuyucu MIFARE kartın da yalnızca **UID**'sini
okur ve UID de kopyalanabilir. Gerçek kriptografik koruma için DESFire + SAM
modülü gerekir; bu da kapalı SDK ve ciddi karmaşıklık demektir.

**Ama sizin durumunuzda buna gerek yok** — çünkü fotoğraf çekiyorsunuz.

> Kopya kartla giren kişinin yüzü kayda giriyor. Fotoğraf, kart kopyalamaya
> karşı DESFire'dan daha pratik ve çok daha ucuz bir savunma. Zaten istediğiniz
> özellik, aynı zamanda güvenlik probleminizi de çözüyor.

Bu yüzden: MIFARE UID + fotoğraf. DESFire'a gerek yok.

---

## Saat senkronizasyonu — atlanırsa her şeyi bozar

Her terminalde **NTP zorunludur**. Terminal saati 10 dakika kayarsa o kapıdan
geçen herkesin puantajı 10 dakika yanlış olur ve bunu aylar sonra fark
edersiniz.

```bash
sudo timedatectl set-ntp true
# Kurum içi NTP sunucunuz varsa /etc/systemd/timesyncd.conf içine yazın
```

Sunucu tarafı ayrıca kendini korur: gelecek tarihli okuma geldiğinde log'a
uyarı düşer (`app/api/ingest.py`). Yine de asıl çözüm NTP'dir.

---

## Kurulum (Raspberry Pi / Debian / Ubuntu)

```bash
# PC/SC okuyucu için
sudo apt install pcscd libccid python3-pip
sudo systemctl enable --now pcscd

# Agent
cd edge
pip install -e ".[camera,pcsc]"

# Kamera ve okuyucu erişimi için kullanıcıyı gruplara ekleyin
sudo usermod -aG video,input,plugdev $USER

# Yapılandırma
sudo mkdir -p /etc/pdks-edge /var/lib/pdks-edge
sudo cp config.example.yaml /etc/pdks-edge/config.yaml
sudo nano /etc/pdks-edge/config.yaml   # terminal_code ve api_key

# Çalıştır
python -m pdks_edge --config /etc/pdks-edge/config.yaml
```

### Donanım gelmeden geliştirme

Ekip donanımı beklemeden tüm akışı çalıştırabilir:

```yaml
reader:
  type: mock
  trigger_file: /tmp/pdks_card
camera:
  enabled: false
```

```bash
echo 04A2B3C4D5 > /tmp/pdks_card   # kart okutmakla aynı etki
```

### systemd servisi

```ini
[Unit]
Description=PDKS Edge Agent
After=network-online.target pcscd.service

[Service]
ExecStart=/usr/bin/python3 -m pdks_edge --config /etc/pdks-edge/config.yaml
Restart=always
RestartSec=5
User=pdks
SupplementaryGroups=video input plugdev

[Install]
WantedBy=multi-user.target
```

---

## USB okuyucu yolunu sabitleme

`/dev/input/eventX` numaraları yeniden başlatmada değişebilir. Sabit bir yol
için udev kuralı yazın:

```
# /etc/udev/rules.d/99-pdks-reader.rules
SUBSYSTEM=="input", ATTRS{idVendor}=="XXXX", ATTRS{idProduct}=="YYYY", \
    SYMLINK+="pdks-reader", MODE="0660", GROUP="input"
```

`idVendor` / `idProduct` değerlerini `lsusb` ile öğrenirsiniz. Ardından
yapılandırmada `device_path: /dev/pdks-reader` kullanın.
