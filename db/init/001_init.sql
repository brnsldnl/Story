-- =====================================================================
-- PDKS (Personel Devam Kontrol Sistemi) - Çekirdek şema
--
-- Tasarım ilkesi: HAM VERİ ile HESAPLANMIŞ VERİ kesin olarak ayrılır.
--   card_reads      -> ham okuma, asla UPDATE/DELETE edilmez
--   adjustments     -> manuel düzeltmeler ayrı tabloda, onay zinciriyle
--   attendance_days -> ham veri + düzeltmelerden TÜRETİLİR, her zaman
--                      sıfırdan yeniden hesaplanabilir
--
-- Bu ayrım sayesinde "geçen ayın puantajını yeniden hesapla" her zaman
-- mümkündür ve hiçbir denetim sorusu cevapsız kalmaz.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------
-- Organizasyon: lokasyon ve terminaller
-- Çoklu lokasyon / çoklu okuyucu çekirdekte, sonradan eklenen bir şey değil.
-- ---------------------------------------------------------------------

CREATE TABLE sites (
    id          BIGSERIAL PRIMARY KEY,
    code        TEXT        NOT NULL UNIQUE,
    name        TEXT        NOT NULL,
    timezone    TEXT        NOT NULL DEFAULT 'Europe/Istanbul',
    address     TEXT,
    active      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN sites.timezone IS
    'Lokasyon bazlı saat dilimi. Tüm zamanlar UTC saklanır, gün sınırı '
    'bu saat dilimine göre hesaplanır.';

-- Terminal = bir kapıdaki okuyucu + kamera seti (edge node)
CREATE TABLE terminals (
    id              BIGSERIAL PRIMARY KEY,
    site_id         BIGINT      NOT NULL REFERENCES sites(id),
    code            TEXT        NOT NULL UNIQUE,
    name            TEXT        NOT NULL,
    -- in      : bu terminal her zaman GİRİŞ yazar
    -- out     : her zaman ÇIKIŞ
    -- toggle  : kişinin son yönüne bakarak sırayla giriş/çıkış
    direction_mode  TEXT        NOT NULL DEFAULT 'toggle'
                    CHECK (direction_mode IN ('in', 'out', 'toggle')),
    api_key_hash    TEXT        NOT NULL,
    camera_enabled  BOOLEAN     NOT NULL DEFAULT TRUE,
    last_seen_at    TIMESTAMPTZ,
    agent_version   TEXT,
    active          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_terminals_site ON terminals(site_id);

COMMENT ON COLUMN terminals.last_seen_at IS
    'Edge agent heartbeat. Bir terminal uzun süre veri göndermiyorsa '
    'panelde uyarı çıkar - sessiz veri kaybının tek savunması budur.';

-- ---------------------------------------------------------------------
-- Personel ve kartlar
-- ---------------------------------------------------------------------

CREATE TABLE departments (
    id            BIGSERIAL PRIMARY KEY,
    code          TEXT        NOT NULL UNIQUE,
    name          TEXT        NOT NULL,
    -- Logo tarafındaki LOGICALREF / kod karşılığı
    external_ref  TEXT,
    active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE employees (
    id              BIGSERIAL PRIMARY KEY,
    employee_no     TEXT        NOT NULL UNIQUE,
    first_name      TEXT        NOT NULL,
    last_name       TEXT        NOT NULL,
    department_id   BIGINT      REFERENCES departments(id),
    site_id         BIGINT      REFERENCES sites(id),
    title           TEXT,
    hire_date       DATE,
    termination_date DATE,
    -- Logo'dan gelen kayıtlar için kaynak referansı
    external_ref    TEXT,
    source          TEXT        NOT NULL DEFAULT 'manual'
                    CHECK (source IN ('manual', 'logo')),
    synced_at       TIMESTAMPTZ,
    active          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_employees_department ON employees(department_id);
CREATE INDEX idx_employees_site ON employees(site_id);
CREATE UNIQUE INDEX idx_employees_external_ref
    ON employees(external_ref) WHERE external_ref IS NOT NULL;

-- Kart-personel ilişkisi ZAMAN ARALIKLIDIR.
-- Bir kart kaybolup başka bir personele verildiğinde geçmiş kayıtlar
-- bozulmamalı; bu yüzden ilişki (uid, valid_from, valid_to) üçlüsüdür.
CREATE TABLE cards (
    id           BIGSERIAL PRIMARY KEY,
    uid          TEXT        NOT NULL,
    technology   TEXT        NOT NULL DEFAULT 'mifare'
                 CHECK (technology IN ('mifare', 'em4100', 'desfire', 'other')),
    employee_id  BIGINT      NOT NULL REFERENCES employees(id),
    valid_from   TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to     TIMESTAMPTZ,
    status       TEXT        NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'lost', 'blocked', 'returned')),
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_cards_uid ON cards(uid);
CREATE INDEX idx_cards_employee ON cards(employee_id);

-- Aynı UID aynı anda yalnızca tek bir aktif personele bağlı olabilir
CREATE UNIQUE INDEX idx_cards_uid_active
    ON cards(uid) WHERE status = 'active' AND valid_to IS NULL;

-- ---------------------------------------------------------------------
-- Fotoğraflar (KVKK: saklama süresi ve erişim logu şemanın parçası)
-- ---------------------------------------------------------------------

CREATE TABLE photos (
    id           BIGSERIAL PRIMARY KEY,
    storage_key  TEXT        NOT NULL UNIQUE,
    captured_at  TIMESTAMPTZ NOT NULL,
    sha256       TEXT        NOT NULL,
    byte_size    INTEGER     NOT NULL,
    width        INTEGER,
    height       INTEGER,
    -- KVKK imha politikası: bu tarihten sonra otomatik olarak silinir.
    -- Silme işi nightly job tarafından gerçekten dosyayı siler, sadece
    -- flag atmaz.
    purge_after  TIMESTAMPTZ NOT NULL,
    deleted_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_photos_purge ON photos(purge_after) WHERE deleted_at IS NULL;

-- KVKK: fotoğrafa kim, ne zaman, neden baktı. Denetimde ilk sorulan şey.
CREATE TABLE photo_access_log (
    id           BIGSERIAL PRIMARY KEY,
    photo_id     BIGINT      NOT NULL REFERENCES photos(id),
    user_id      BIGINT      NOT NULL,
    accessed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason       TEXT,
    ip_address   INET
);

CREATE INDEX idx_photo_access_photo ON photo_access_log(photo_id);
CREATE INDEX idx_photo_access_user ON photo_access_log(user_id, accessed_at);

-- ---------------------------------------------------------------------
-- HAM OKUMA - değiştirilemez kayıt
-- ---------------------------------------------------------------------

CREATE TABLE card_reads (
    id               BIGSERIAL PRIMARY KEY,
    terminal_id      BIGINT      NOT NULL REFERENCES terminals(id),
    card_uid         TEXT        NOT NULL,
    -- Okumanın terminalde gerçekleştiği an (offline kuyrukta beklemiş olabilir)
    read_at          TIMESTAMPTZ NOT NULL,
    -- Sunucuya ulaştığı an; read_at ile arasındaki fark offline süreyi verir
    received_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Okuma anında çözümlenen personel. Kart sonradan başkasına devredilse
    -- bile bu kayıt doğru kişiyi göstermeye devam eder.
    employee_id      BIGINT      REFERENCES employees(id),
    direction        TEXT        NOT NULL DEFAULT 'unknown'
                     CHECK (direction IN ('in', 'out', 'unknown')),
    photo_id         BIGINT      REFERENCES photos(id),
    -- Edge agent tarafından üretilen benzersiz olay kimliği.
    -- Offline kuyruk yeniden gönderim yaptığında mükerrer kayıt oluşmasını
    -- engelleyen tek mekanizma budur.
    client_event_id  UUID        NOT NULL,
    -- Tanınmayan kart, süresi dolmuş kart vb. durumlar
    reject_reason    TEXT,
    raw              JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_card_reads_idempotency
    ON card_reads(terminal_id, client_event_id);
CREATE INDEX idx_card_reads_employee_time ON card_reads(employee_id, read_at);
CREATE INDEX idx_card_reads_terminal_time ON card_reads(terminal_id, read_at);

COMMENT ON TABLE card_reads IS
    'Değiştirilemez ham kayıt. Bu tabloya UPDATE veya DELETE uygulanmaz; '
    'düzeltmeler adjustments tablosuna yazılır.';

-- ---------------------------------------------------------------------
-- Vardiya, tatil, izin
-- ---------------------------------------------------------------------

CREATE TABLE shifts (
    id                   BIGSERIAL PRIMARY KEY,
    code                 TEXT    NOT NULL UNIQUE,
    name                 TEXT    NOT NULL,
    start_time           TIME    NOT NULL,
    end_time             TIME    NOT NULL,
    -- Gece vardiyası (22:00-06:00) gün sınırını aşar; puantajda en çok
    -- hata yapılan yer burasıdır.
    crosses_midnight     BOOLEAN NOT NULL DEFAULT FALSE,
    -- 'auto'   : süreden otomatik kesilir
    -- 'card'   : mola giriş/çıkışı da kartla okutulur
    -- 'none'   : mola kesintisi yok
    break_mode           TEXT    NOT NULL DEFAULT 'auto'
                         CHECK (break_mode IN ('auto', 'card', 'none')),
    break_minutes        INTEGER NOT NULL DEFAULT 60,
    -- Tolerans: bu süre içindeki gecikme "geç kalma" sayılmaz
    grace_in_minutes     INTEGER NOT NULL DEFAULT 0,
    grace_out_minutes    INTEGER NOT NULL DEFAULT 0,
    -- Yuvarlama: 15 ise 08:57 -> 09:00
    rounding_minutes     INTEGER NOT NULL DEFAULT 0,
    -- Bu eşiğin altındaki fazla kalmalar mesai sayılmaz
    min_overtime_minutes INTEGER NOT NULL DEFAULT 15,
    -- Mesai için amir onayı zorunlu mu? Zorunluysa onaysız fazla kalma
    -- ücretlendirilmez.
    overtime_requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
    active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Personelin hangi tarih aralığında hangi vardiyada olduğu
CREATE TABLE shift_assignments (
    id           BIGSERIAL PRIMARY KEY,
    employee_id  BIGINT  NOT NULL REFERENCES employees(id),
    shift_id     BIGINT  NOT NULL REFERENCES shifts(id),
    date_from    DATE    NOT NULL,
    date_to      DATE,
    -- Haftanın hangi günleri geçerli: bit maskesi, Pazartesi = 1. bit
    -- 0b0111110 = 62 -> Pazartesi-Cuma
    weekday_mask INTEGER NOT NULL DEFAULT 62,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_shift_assignments_employee
    ON shift_assignments(employee_id, date_from);

CREATE TABLE holidays (
    id       BIGSERIAL PRIMARY KEY,
    date     DATE    NOT NULL,
    name     TEXT    NOT NULL,
    -- half = arife günü yarım gün
    type     TEXT    NOT NULL DEFAULT 'public'
             CHECK (type IN ('public', 'half')),
    -- NULL ise tüm lokasyonlar için geçerli
    site_id  BIGINT  REFERENCES sites(id),
    UNIQUE (date, site_id)
);

CREATE TABLE leaves (
    id           BIGSERIAL PRIMARY KEY,
    employee_id  BIGINT      NOT NULL REFERENCES employees(id),
    leave_type   TEXT        NOT NULL
                 CHECK (leave_type IN ('annual', 'unpaid', 'sick',
                                       'excused', 'duty', 'maternity')),
    start_at     TIMESTAMPTZ NOT NULL,
    end_at       TIMESTAMPTZ NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    reason       TEXT,
    created_by   BIGINT,
    approved_by  BIGINT,
    approved_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_leaves_employee_range ON leaves(employee_id, start_at, end_at);

-- ---------------------------------------------------------------------
-- Düzeltmeler ve mesai onayı
-- Ham veri asla bozulmaz; düzeltme burada yaşar, motor ikisini birleştirir.
-- ---------------------------------------------------------------------

CREATE TABLE adjustments (
    id           BIGSERIAL PRIMARY KEY,
    employee_id  BIGINT      NOT NULL REFERENCES employees(id),
    work_date    DATE        NOT NULL,
    -- add_in / add_out : unutulan okutmayı tamamlar
    -- set_status       : günü izinli/görevli vb. olarak işaretler
    -- ignore_read      : hatalı bir ham okumayı hesap dışı bırakır
    type         TEXT        NOT NULL
                 CHECK (type IN ('add_in', 'add_out', 'set_status', 'ignore_read')),
    payload      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    reason       TEXT        NOT NULL,
    state        TEXT        NOT NULL DEFAULT 'pending'
                 CHECK (state IN ('pending', 'approved', 'rejected')),
    created_by   BIGINT      NOT NULL,
    approved_by  BIGINT,
    approved_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_adjustments_employee_date ON adjustments(employee_id, work_date);

CREATE TABLE overtime_approvals (
    id                BIGSERIAL PRIMARY KEY,
    employee_id       BIGINT      NOT NULL REFERENCES employees(id),
    work_date         DATE        NOT NULL,
    requested_minutes INTEGER     NOT NULL,
    approved_minutes  INTEGER     NOT NULL DEFAULT 0,
    approved_by       BIGINT,
    approved_at       TIMESTAMPTZ,
    note              TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (employee_id, work_date)
);

-- ---------------------------------------------------------------------
-- HESAPLANMIŞ GÜN - türetilmiş veri, her zaman yeniden üretilebilir
-- ---------------------------------------------------------------------

CREATE TABLE attendance_days (
    id                  BIGSERIAL PRIMARY KEY,
    employee_id         BIGINT  NOT NULL REFERENCES employees(id),
    work_date           DATE    NOT NULL,
    shift_id            BIGINT  REFERENCES shifts(id),

    first_in_at         TIMESTAMPTZ,
    last_out_at         TIMESTAMPTZ,

    worked_minutes      INTEGER NOT NULL DEFAULT 0,
    break_minutes       INTEGER NOT NULL DEFAULT 0,
    late_minutes        INTEGER NOT NULL DEFAULT 0,
    early_leave_minutes INTEGER NOT NULL DEFAULT 0,

    -- Mesai kırılımı: farklı ücret katsayıları farklı kolonlar
    normal_minutes      INTEGER NOT NULL DEFAULT 0,
    -- Haftalık 45 saatin altında kalan fazla süre (farklı katsayı)
    extra_minutes       INTEGER NOT NULL DEFAULT 0,
    -- 45 saat üstü fazla çalışma
    overtime_minutes    INTEGER NOT NULL DEFAULT 0,
    -- 20:00-06:00 arası çalışma
    night_minutes       INTEGER NOT NULL DEFAULT 0,
    weekend_minutes     INTEGER NOT NULL DEFAULT 0,
    holiday_minutes     INTEGER NOT NULL DEFAULT 0,
    -- Onaylanmamış fazla kalma: raporlanır ama ücretlendirilmez
    unapproved_overtime_minutes INTEGER NOT NULL DEFAULT 0,

    status              TEXT    NOT NULL DEFAULT 'ok'
                        CHECK (status IN ('ok', 'missing_out', 'missing_in',
                                          'absent', 'leave', 'holiday',
                                          'weekend', 'not_scheduled')),
    has_adjustment      BOOLEAN NOT NULL DEFAULT FALSE,
    -- Motor sürümü: hesap kuralları değişince hangi kayıtların yeniden
    -- hesaplanması gerektiği buradan anlaşılır
    engine_version      INTEGER NOT NULL DEFAULT 1,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (employee_id, work_date)
);

CREATE INDEX idx_attendance_date ON attendance_days(work_date);
CREATE INDEX idx_attendance_status ON attendance_days(status, work_date);

COMMENT ON TABLE attendance_days IS
    'Türetilmiş tablo. card_reads + adjustments + shifts + leaves girdileriyle '
    'her zaman sıfırdan yeniden hesaplanabilir. Elle düzenlenmez.';

-- ---------------------------------------------------------------------
-- Kullanıcılar, roller ve yetki kapsamı
-- Çoklu lokasyonda "tek panel" ancak kapsam kısıtlamasıyla anlamlı:
-- genel müdür hepsini görür, şube amiri yalnızca kendi şubesini.
-- ---------------------------------------------------------------------

CREATE TABLE users (
    id             BIGSERIAL PRIMARY KEY,
    email          TEXT        NOT NULL UNIQUE,
    password_hash  TEXT        NOT NULL,
    full_name      TEXT        NOT NULL,
    -- admin      : her şey
    -- hr         : tüm personel + fotoğraf görüntüleme
    -- manager    : yalnızca kapsamındaki lokasyon/departman, fotoğraf YOK
    -- employee   : yalnızca kendi kayıtları (self-servis portal)
    role           TEXT        NOT NULL DEFAULT 'manager'
                   CHECK (role IN ('admin', 'hr', 'manager', 'employee')),
    -- employee rolü için kendi personel kaydına bağlantı
    employee_id    BIGINT      REFERENCES employees(id),
    active         BOOLEAN     NOT NULL DEFAULT TRUE,
    last_login_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_site_scopes (
    user_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    site_id  BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, site_id)
);

CREATE TABLE user_department_scopes (
    user_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    department_id  BIGINT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, department_id)
);

-- ---------------------------------------------------------------------
-- Denetim izi ve entegrasyon çalışmaları
-- ---------------------------------------------------------------------

CREATE TABLE audit_log (
    id             BIGSERIAL PRIMARY KEY,
    actor_user_id  BIGINT,
    action         TEXT        NOT NULL,
    entity         TEXT        NOT NULL,
    entity_id      TEXT,
    before_data    JSONB,
    after_data     JSONB,
    ip_address     INET,
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_entity ON audit_log(entity, entity_id);
CREATE INDEX idx_audit_time ON audit_log(occurred_at);

CREATE TABLE sync_runs (
    id           BIGSERIAL PRIMARY KEY,
    kind         TEXT        NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    status       TEXT        NOT NULL DEFAULT 'running'
                 CHECK (status IN ('running', 'success', 'failed')),
    stats        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    error        TEXT
);

CREATE INDEX idx_sync_runs_kind ON sync_runs(kind, started_at);
