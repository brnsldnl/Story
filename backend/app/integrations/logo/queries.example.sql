-- Logo Tiger personel okuma sorgusu - ÖRNEK
--
-- Bu sorgu KODA GÖMÜLÜ DEĞİLDİR; ortam değişkeni/yapılandırma ile verilir.
-- Sebep: Logo tablo isimleri firma numarası ve dönem içerir (LG_001_...),
-- sürümler arasında değişir, her kurulumda farklı alanlar kullanılır.
--
-- KURULUMDA YAPILACAK: Aşağıdaki sorguyu kendi Logo kurulumunuza göre
-- düzenleyin. Firma numarasını (001) ve tablo/alan adlarını kendi
-- veritabanınızdan doğrulayın:
--
--   SELECT name FROM sys.tables WHERE name LIKE 'LG_%' ORDER BY name;
--
-- Sorgunun döndürmesi GEREKEN kolon adları (diğerleri yok sayılır):
--   external_ref      -> Logo LOGICALREF (eşleştirme anahtarı, zorunlu)
--   employee_no       -> personel/sicil kodu (zorunlu)
--   first_name        -> ad
--   last_name         -> soyad
--   department_code   -> departman kodu (opsiyonel)
--   department_name   -> departman adı (opsiyonel)
--   title             -> görev/unvan (opsiyonel)
--   active            -> 1/0 aktiflik (opsiyonel, varsayılan 1)

SELECT
    E.LOGICALREF        AS external_ref,
    E.CODE              AS employee_no,
    E.NAME              AS first_name,
    E.SURNAME           AS last_name,
    D.CODE              AS department_code,
    D.NAME              AS department_name,
    E.TITLE             AS title,
    CASE WHEN E.ACTIVE = 0 THEN 1 ELSE 0 END AS active
FROM LG_001_EMPLOYEE AS E
LEFT JOIN LG_001_DEPARTMENT AS D
    ON D.LOGICALREF = E.DEPARTMENTREF;

-- NOT: Logo'da ACTIVE alanı çoğu tabloda TERS çalışır (0 = aktif).
-- Yukarıdaki CASE bunu düzeltir, ancak kendi kurulumunuzda mutlaka
-- doğrulayın: yanlış yorumlama tüm personeli pasife çeker.
