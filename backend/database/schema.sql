
-- ============================================================
-- DATABASE SCHEMA
-- CO2 Classroom IoT & GRU Prediction System
-- Version: V4.3
-- ============================================================
--
-- Waktu disimpan sebagai teks ISO 8601 UTC.
-- Contoh: 2026-11-08T03:30:00Z
--
-- Referensi kontrak data:
-- docs/02-kontrak-data.md
--
-- Catatan:
-- 1. ts_utc merupakan waktu efektif pembacaan sensor.
-- 2. received_at merupakan waktu penerimaan di backend.
-- 3. measured_at_utc merupakan waktu pengukuran asli dari
--    ESP32 jika waktu perangkat telah tersinkronisasi.
-- 4. Data legacy V4.2 tetap didukung.
-- 5. Migrasi database lama dilakukan menggunakan skrip
--    migrasi terpisah, bukan dengan schema.sql.
-- ============================================================

PRAGMA journal_mode = WAL;


-- ============================================================
-- 1. SENSOR READING
-- ============================================================

CREATE TABLE IF NOT EXISTS sensor_reading (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identitas ruangan dan perangkat
    room_id         TEXT NOT NULL,
    device_id       TEXT NOT NULL,

    -- Metadata pesan
    seq             INTEGER,
    boot_id         TEXT,
    uptime_ms       INTEGER,

    -- Timestamp
    ts_utc          TEXT NOT NULL,
    received_at     TEXT NOT NULL,
    measured_at_utc TEXT,

    -- Sensor CO2
    co2_ppm         INTEGER,

    -- Sensor DHT22
    temp_in_c       REAL,
    hum_in_pct      REAL,

    -- Sensor lingkungan luar (opsional)
    temp_out_c      REAL,
    hum_out_pct     REAL,

    -- Sensor PIR
    pir             INTEGER,

    -- Wi-Fi signal strength
    rssi            INTEGER,

    -- Informasi kesalahan sensor (JSON array)
    faults          TEXT NOT NULL DEFAULT '[]',

    -- Penanda kualitas data (JSON array)
    -- Contoh: suspect, ts_corrected, ...
    quality_flags   TEXT NOT NULL DEFAULT '[]',

    -- Payload MQTT asli untuk audit
    raw             TEXT NOT NULL
);


-- Query data berdasarkan ruangan dan waktu
CREATE INDEX IF NOT EXISTS idx_reading_room_ts
ON sensor_reading (room_id, ts_utc);


-- Deduplikasi payload legacy (V4.2 dan sebelumnya)
-- Berlaku hanya jika boot_id tidak tersedia.
CREATE UNIQUE INDEX IF NOT EXISTS idx_reading_dedup
ON sensor_reading (device_id, ts_utc, seq)
WHERE boot_id IS NULL;


-- Deduplikasi payload V4.3
-- Setiap sesi boot memiliki identitas berbeda.
-- Nomor urut yang sama dari sesi boot berbeda tetap valid.
CREATE UNIQUE INDEX IF NOT EXISTS idx_reading_device_boot_seq
ON sensor_reading (device_id, boot_id, seq)
WHERE boot_id IS NOT NULL
  AND seq IS NOT NULL;


-- ============================================================
-- 2. PREDICTION
-- ============================================================

CREATE TABLE IF NOT EXISTS prediction (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identitas ruangan
    room_id     TEXT NOT NULL,

    -- Waktu prediksi dibuat
    created_at  TEXT NOT NULL,

    -- Waktu yang diprediksi
    target_ts   TEXT NOT NULL,

    -- Horizon prediksi (1 sampai 15 menit)
    horizon_min INTEGER NOT NULL,

    -- Hasil prediksi konsentrasi CO2
    co2_ppm     REAL NOT NULL,

    -- Model yang digunakan
    model       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prediction_room_created
ON prediction (room_id, created_at);


-- ============================================================
-- 3. RECOMMENDATION
-- ============================================================

CREATE TABLE IF NOT EXISTS recommendation (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identitas ruangan
    room_id                TEXT NOT NULL,

    -- Waktu rekomendasi dibuat
    created_at             TEXT NOT NULL,

    -- none  : kondisi aman
    -- watch : perlu pemantauan
    -- flush : rekomendasi membuka ventilasi
    action                 TEXT NOT NULL
                           CHECK (action IN ('none', 'watch', 'flush')),

    -- Durasi rekomendasi ventilasi (menit)
    minutes                INTEGER NOT NULL,

    -- Prediksi CO2 tertinggi
    predicted_peak_ppm     REAL NOT NULL,

    -- Prediksi CO2 pada t+15 menit
    predicted_at_15min_ppm REAL NOT NULL,

    -- Model yang menghasilkan rekomendasi
    model                  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_recommendation_room_created
ON recommendation (room_id, created_at);


-- ============================================================
-- 4. MANUAL EVENT
-- ============================================================
--
-- Digunakan untuk pencatatan kondisi dan aktivitas ruangan.
-- Data ini dapat digunakan untuk analisis eksperimen,
-- tetapi tidak harus menjadi input model GRU.
-- ============================================================

CREATE TABLE IF NOT EXISTS manual_event (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identitas ruangan
    room_id                TEXT NOT NULL,

    -- Waktu kejadian
    ts_utc                 TEXT NOT NULL,

    -- Jenis kejadian
    jenis                  TEXT NOT NULL,

    -- Perkiraan jumlah orang
    jumlah_orang_perkiraan INTEGER,

    -- Keterangan tambahan
    catatan                TEXT,

    -- Identitas pencatat
    pencatat               TEXT
);
