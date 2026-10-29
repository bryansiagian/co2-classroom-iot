-- Skema SQLite untuk TA CO2 ruang kelas.
-- Waktu disimpan sebagai teks ISO 8601 UTC (contoh 2026-10-19T04:30:00Z) agar urut secara leksikografis.
-- Pemetaan tabel dan field mengikuti docs/02-kontrak-data.md.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS sensor_reading (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id       TEXT    NOT NULL,
    device_id     TEXT    NOT NULL,
    seq           INTEGER,
    ts_utc        TEXT    NOT NULL,   -- waktu efektif (dari ESP32, atau waktu terima jika ts tidak valid)
    received_at   TEXT    NOT NULL,   -- waktu pesan diterima backend
    co2_ppm       INTEGER,
    temp_in_c     REAL,
    hum_in_pct    REAL,
    temp_out_c    REAL,
    hum_out_pct   REAL,
    pir           INTEGER,
    rssi          INTEGER,
    faults        TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    quality_flags TEXT    NOT NULL DEFAULT '[]',  -- JSON array: suspect, ts_corrected, ...
    raw           TEXT    NOT NULL                -- pesan mentah, tidak pernah diubah
);
CREATE INDEX IF NOT EXISTS idx_reading_room_ts ON sensor_reading (room_id, ts_utc);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reading_dedup ON sensor_reading (device_id, ts_utc, seq);

CREATE TABLE IF NOT EXISTS prediction (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,   -- kapan prediksi dibuat
    target_ts   TEXT    NOT NULL,   -- waktu yang diprediksi
    horizon_min INTEGER NOT NULL,   -- 1 sampai 15
    co2_ppm     REAL    NOT NULL,
    model       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prediction_room_created ON prediction (room_id, created_at);

CREATE TABLE IF NOT EXISTS recommendation (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id                TEXT    NOT NULL,
    created_at             TEXT    NOT NULL,
    action                 TEXT    NOT NULL CHECK (action IN ('none', 'watch', 'flush')),
    minutes                INTEGER NOT NULL,
    predicted_peak_ppm     REAL    NOT NULL,
    predicted_at_15min_ppm REAL    NOT NULL,
    model                  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recommendation_room_created ON recommendation (room_id, created_at);

CREATE TABLE IF NOT EXISTS manual_event (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id                TEXT NOT NULL,
    ts_utc                 TEXT NOT NULL,
    jenis                  TEXT NOT NULL,
    jumlah_orang_perkiraan INTEGER,
    catatan                TEXT,
    pencatat               TEXT
);
