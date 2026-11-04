# Deployment Backend dan Backup pada Server H200

**Lingkungan yang diuji:** server kampus Ubuntu, user `bryan`, repository di `/home/bryan/co2-classroom-iot`. Dokumen ini mencatat setup yang berhasil diverifikasi pada **4 November 2026**, bukan panduan otomatis untuk semua server.

## 1. Prasyarat

- Akses SSH dan izin `sudo` yang diperlukan.
- Python 3.14.4 (lingkungan yang diuji), Git, dan jaringan ke broker Mosquitto.
- Mosquitto yang sudah dikonfigurasi terpisah untuk TLS pada `172.22.44.29:8883`.
- Kredensial MQTT backend serta sertifikat publik yang sesuai.
- Repository `https://github.com/bryansiagian/co2-classroom-iot`.

**Keamanan:** jangan menyalin password ke dokumentasi, chat publik, Git, atau command line shell yang terekam history. Hanya file `.env` lokal untuk kredensial. Jika menginstal di host lain, ubah alamat dan path seperlunya.

## 2. Clone dan dependensi

```bash
cd ~
git clone https://github.com/bryansiagian/co2-classroom-iot.git
cd ~/co2-classroom-iot/backend/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Jika repository sudah ada, gunakan `git status`, `git fetch`, lalu sinkronkan dengan hati-hati. Jangan menghapus database lokal atau perubahan server.

## 3. Konfigurasi environment

Contoh sumber konfigurasi tersedia pada `backend/.env.example`. Kode `app/config.py` membaca **dua** lokasi: `backend/.env` dan `backend/backend/.env`, dengan file yang kedua bisa menimpa nilai pertama. Untuk mencegah kebingungan, pilih **satu lokasi aktif**; konfigurasi pengujian H200 memakai `backend/.env`.

Contoh variabel penting (nilai rahasia sengaja disamarkan):

```dotenv
ROOM_ID=gd525
ROOM_LABEL=GD 525
MQTT_ENABLED=true
MQTT_HOST=172.22.44.29
MQTT_PORT=8883
MQTT_USERNAME=backend_gd525
MQTT_PASSWORD=REPLACE_WITH_REAL_SECRET
MQTT_TOPIC_PREFIX=classroom
MQTT_SENSOR_TOPIC=classroom/gd525/sensors
MQTT_TLS_ENABLED=true
MQTT_CA_CERT=certs/server.crt
PREDICTOR=persistence
```

Jika membuat `backend/.env`:

```bash
cd ~/co2-classroom-iot/backend
cp .env.example .env
nano .env
chmod 600 .env
```

Jangan mengaktifkan `backend/backend/.env` kedua yang berisi `MQTT_HOST=localhost` dan `MQTT_PORT=1883` karena akan menimpa nilai H200. Pastikan `backend/backend/certs/server.crt` ada dan merupakan sertifikat publik broker yang benar.

Verifikasi tanpa mencetak password:

```bash
cd ~/co2-classroom-iot/backend/backend
.venv/bin/python -c "from app.config import settings; print(settings.mqtt_host, settings.mqtt_port, settings.mqtt_tls_enabled, settings.db_path)"
```

Target untuk lingkungan ini: `172.22.44.29 8883 True` dan path DB di `backend/backend/data/co2class.db`.

## 4. Uji FastAPI manual

```bash
cd ~/co2-classroom-iot/backend/backend
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Periksa pesan startup FastAPI dan `MQTT tersambung`. Jika broker menerima ESP32, periksa isi database melalui terminal SSH kedua:

```bash
cd ~/co2-classroom-iot/backend/backend
python3 - <<'PY'
import sqlite3
with sqlite3.connect('data/co2class.db') as c:
    for t in ('sensor_reading', 'prediction', 'recommendation'):
        print(t, c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
PY
```

Saat pengujian terdokumentasi, penambahan data dalam 30 detik adalah **+3 sensor, +45 prediksi, +3 rekomendasi**. Ini hasil pengujian singkat, bukan jaminan uptime 4 minggu. Hentikan Uvicorn manual (`Ctrl+C`) sebelum memakai service systemd.

## 5. Menjalankan dengan systemd

File template yang dicatat bersama proyek:

```text
deployment/systemd/co2class-backend.service
deployment/systemd/co2class-backup.service
deployment/systemd/co2class-backup.timer
```

Periksa isi file (khususnya `User`, `WorkingDirectory`, dan `ExecStart`) sebelum memasang:

```bash
cd ~/co2-classroom-iot
sudo cp deployment/systemd/co2class-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now co2class-backend.service
sudo systemctl status co2class-backend --no-pager
```

Service yang diuji menjalankan:

```bash
/home/bryan/co2-classroom-iot/backend/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Pantau log:

```bash
sudo journalctl -u co2class-backend -n 50 --no-pager
sudo journalctl -u co2class-backend -f
```

`active (running)` dan pesan MQTT tersambung telah diamati pada pengujian H200. Jika muncul `MQTT terputus (Unspecified error)` secara berulang, investigasi broker, jaringan, dan potensi penggunaan MQTT client ID ganda.

## 6. Backup SQLite dan timer harian

Script `backups/backup_db.py` menggunakan **SQLite Backup API** dari DB aktif ke berkas backup bernama timestamp UTC. Cara ini lebih aman daripada `cp` database saat terjadi penulisan, terutama pada mode WAL.

Uji manual:

```bash
cd ~/co2-classroom-iot
python3 backups/backup_db.py
ls -lh backups/
```

Pasang template service dan timer (periksa isinya terlebih dahulu):

```bash
sudo cp deployment/systemd/co2class-backup.service /etc/systemd/system/
sudo cp deployment/systemd/co2class-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now co2class-backup.timer
systemctl list-timers --all | grep co2class
sudo systemctl start co2class-backup.service
sudo systemctl status co2class-backup.service --no-pager
```

Timer yang diuji memakai `OnCalendar=*-*-* 17:00:00 UTC` (sama dengan **00.00 WIB hari berikutnya**). Pada `Type=oneshot`, status `inactive (dead)` setelah selesai adalah normal jika exit code `0/SUCCESS`.

**Batasan backup saat ini:** file hasil backup masih di server H200 yang sama, tidak ada retensi otomatis, uji restore terdokumentasi, atau backup off-server. Implementasikan semua itu sebelum mengandalkan pengumpulan 4 minggu.

## 7. Pemeriksaan data dan troubleshooting

| Gejala | Pemeriksaan |
|---|---|
| `ModuleNotFoundError: app` | Jalankan dari `backend/backend/` |
| MQTT ke `localhost:1883` | Cari `.env` ganda dan cek nilai konfigurasi efektif |
| `Connection refused` port 1883 | Broker penelitian menggunakan port TLS 8883 pada IP H200 |
| Sertifikat tidak ditemukan | Cek `backend/backend/certs/server.crt` dan `WorkingDirectory` |
| `no such table` | Periksa inisialisasi schema dan path SQLite, jangan buat schema berbeda sembarangan |
| Service restart berulang | `journalctl`, izin file, Python virtual environment, port 8000 |
| Client MQTT sering putus | Pastikan hanya satu backend dengan client ID sama |
| Database tidak bertambah | Periksa ESP32, broker, service, validasi payload, dan timestamp |

Periksa port broker:

```bash
sudo ss -lntp | grep -E '1883|8883'
```

**Jangan** memasukkan token/PAT ke remote URL Git; gunakan prompt credential, SSH key, atau credential helper yang aman.

## 8. Checklist sebelum operasi penelitian

- [x] Clone repository, virtual environment, dependensi backend.
- [x] Koneksi FastAPI ↔ MQTT TLS H200.
- [x] SQLite menerima data sensor dan menghasilkan baseline/rekomendasi.
- [x] systemd backend berjalan dan `enabled`.
- [x] Backup manual serta systemd timer berhasil diuji.
- [ ] Uji ketahanan restart/reconnect berulang dan monitoring data hilang.
- [ ] Sumber waktu perangkat yang andal; fallback waktu kompilasi bukan solusi final.
- [ ] Backup off-server, retensi, dan uji pemulihan database.
- [x] Audit awal development dan preprocessing 1 menit (manual, 2 unit test lulus).
- [ ] Penentuan awal periode pengumpulan resmi dan validasi data di GD525.

## 9. Tautan

- [Arsitektur](architecture.md)
- [Pengumpulan data](data-collection.md)
- [Roadmap](development-roadmap.md)

## 10. Catatan migrasi dokumentasi

Panduan historis `05-setup-dan-operasional.md` menggambarkan collector V3 berumur 15 menit. Saat ini sumber penyimpanan utama adalah backend FastAPI pada H200 melalui `systemd`, bukan `~/gd525-iot-test/collector.py`. Skrip dan database lama tetap arsip, bukan sumber penelitian resmi. Lihat [kontrak data](data-contract.md) dan [keputusan/risiko](decisions-and-risks.md).
