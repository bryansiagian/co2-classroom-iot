# CO₂ Classroom IoT — Prediksi CO₂ dan Rekomendasi Ventilasi Proaktif

> Proyek tugas akhir D3 Teknologi Informasi, Institut Teknologi Del. Dokumentasi ini menggambarkan status pengembangan **per 4 November 2026**; fitur yang direncanakan tidak boleh dianggap sudah diuji atau digunakan dalam produksi.

## Gambaran umum

Sistem memantau konsentrasi CO₂, suhu, kelembapan relatif, dan indikator gerakan di ruang kelas GD525. ESP32 menerbitkan pembacaan melalui MQTT dengan TLS ke broker Mosquitto pada server kampus H200. Backend Python/FastAPI menerima pembacaan, menyimpannya ke SQLite, menjalankan prediksi awal menggunakan **persistence baseline**, dan membuat rekomendasi ventilasi. Tujuan penelitian berikutnya adalah prediksi konsentrasi CO₂ horizon **15 menit** menggunakan **Gated Recurrent Unit (GRU)** dan rekomendasi proaktif melalui dashboard serta indikator LED.

**Yang sudah diverifikasi:** sensor → ESP32 → MQTT TLS → backend FastAPI pada H200 → SQLite → prediksi persistence → tabel rekomendasi; backend berjalan sebagai layanan systemd; backup SQLite manual dan timer harian telah diuji.

**Belum diverifikasi/selesai:** model GRU terlatih pada data nyata, efektivitas rekomendasi, dashboard end-to-end dan LED proaktif, keandalan pengumpulan data 4 minggu, backup off-server, dan sinkronisasi waktu perangkat yang memadai untuk deployment jangka panjang.

## Komponen teknologi

| Lapisan | Teknologi | Keterangan |
|---|---|---|
| Perangkat | ESP32 DevKit1 | Firmware pemantauan kontinu V4.1 diuji |
| Sensor CO₂ | MH-Z19C (NDIR) | UART ESP32: RX GPIO26, TX GPIO25 |
| Sensor lingkungan | DHT22 | GPIO4 |
| Indikator aktivitas | PIR HC-SR501 | GPIO27; **bukan** penghitung orang |
| Jaringan | Wi-Fi dan MQTT TLS | Topik `classroom/gd525/sensors`, port TLS `8883` pada deployment kampus |
| Backend | FastAPI + Paho MQTT | Consumer MQTT, validasi, penyimpanan, prediksi, rekomendasi |
| Penyimpanan | SQLite | Data sensor, prediksi, dan rekomendasi |
| ML | Persistence (aktif), GRU (direncanakan) | Target prediksi t+15 menit; interval dataset target 1 menit |
| Antarmuka | Next.js | Pengembangan/validasi integrasi masih berlanjut |
| Deployment | systemd di Ubuntu/H200 | Backend dan backup terjadwal |

## Alur data

```text
ESP32 (MH-Z19C, DHT22, PIR)
    └─ MQTT/TLS → Mosquitto (H200)
                    └─ FastAPI MQTT consumer
                        ├─ SQLite: sensor_reading
                        ├─ baseline: prediction
                        └─ aturan: recommendation
                                 └─ dashboard/LED (integrasi lanjutan)
```

Firmware saat ini mengirim JSON setiap sekitar **10 detik**, misalnya:

```json
{"co2": 1048, "temperature": 26.70, "humidity": 74.40, "pir": 0}
```

Backend mengisi waktu penerimaan UTC bila payload ESP32 belum memiliki timestamp tepercaya; kondisi ini dapat ditandai `ts_corrected`. Data 10 detik perlu diproses menjadi grid **1 menit** sebelum digunakan untuk eksperimen GRU.

## Struktur repository

```text
co2-classroom-iot/
├── backend/
│   ├── .env.example
│   ├── backend/
│   │   ├── app/
│   │   ├── certs/server.crt
│   │   └── requirements.txt
│   └── database/schema.sql
├── frontend/
├── firmware/
├── ml/
├── docs/
├── deployment/systemd/
└── backups/backup_db.py
```

`data/`, `*.db`, `*.db-wal`, `*.db-shm`, `.env`, `.venv`, serta file rahasia firmware **tidak boleh di-commit**. Contoh konfigurasi publik boleh disimpan tanpa kredensial asli.

## Menjalankan backend untuk pengembangan

Jalankan dari **direktori `backend/backend`**:

```bash
cd backend/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Salin dan lengkapi contoh konfigurasi yang tersedia di `backend/.env.example`; gunakan lokasi `backend/.env` **atau** `backend/backend/.env` secara konsisten. File `app/config.py` membaca keduanya, dan file yang lebih dalam memiliki prioritas bila keduanya ada.

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Jangan menjalankan Uvicorn manual bersamaan dengan service systemd yang menggunakan client ID MQTT sama. Untuk deployment H200, baca [panduan deployment](docs/deployment-h200.md).

## Dokumentasi

- [Arsitektur dan aliran data](docs/architecture.md)
- [Deployment backend dan backup di H200](docs/deployment-h200.md)
- [Metode pengumpulan dan kualitas data](docs/data-collection.md)
- [Roadmap dan status pekerjaan](docs/development-roadmap.md)

## Ruang lingkup penelitian

Pengumpulan data difokuskan pada **satu ruang kelas**. PIR merekam indikasi gerakan, bukan jumlah penghuni. Sistem memberikan rekomendasi; tidak mengendalikan ventilasi otomatis. Ambang operasional penelitian yang direncanakan: `<800 ppm` aman, `800–999 ppm` waspada, `≥1000 ppm` rekomendasi ventilasi, dan `≥1500 ppm` kritis. Ambang tersebut adalah **aturan operasional proyek untuk diuji**, bukan klaim batas keselamatan atau standar hukum yang universal.

## Kontribusi dan keamanan

Gunakan commit kecil dengan tujuan jelas. Jangan mengunggah password MQTT, token GitHub, kunci privat, atau database penelitian. Bila kredensial pernah ter-commit, lakukan rotasi kredensial; menambahkan `.gitignore` tidak menghapusnya dari riwayat Git.
