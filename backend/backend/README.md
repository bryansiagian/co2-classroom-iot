# Backend: MQTT, Prediksi, dan REST API

Menerima pesan sensor dari ESP32 lewat MQTT, menyimpan ke SQLite, membuat prediksi CO₂ 15 menit
dan rekomendasi ventilasi, lalu menyediakan REST API untuk dashboard. Format data mengikuti
[docs/02-kontrak-data.md](../docs/02-kontrak-data.md).

## Menjalankan (Windows, dari folder `backend`)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy ..\.env.example ..\.env
```

### A. Tanpa broker MQTT (paling cepat, untuk melihat dashboard hidup)

```powershell
$env:MQTT_ENABLED="false"; $env:PREDICTOR="linear"
python -m tools.seed_db --hours 6 --reset
uvicorn app.main:app --reload --port 8000
```

Lalu di folder `frontend`, buat `.env.local` berisi `NEXT_PUBLIC_API_URL=http://localhost:8000` dan jalankan `npm run dev`.
Label "Data simulasi" di dashboard akan berubah menjadi "Data langsung".

Di Command Prompt (bukan PowerShell), ganti baris pertama dengan `set MQTT_ENABLED=false` dan `set PREDICTOR=linear`.

### B. Dengan broker MQTT (jalur lengkap)

1. Pasang Mosquitto (https://mosquitto.org/download/) dan jalankan `mosquitto -v` di terminal terpisah.
   Pengaturan bawaan hanya menerima koneksi dari komputer yang sama, cukup untuk uji lokal.
2. Terminal 1, di folder `backend`: `uvicorn app.main:app --reload --port 8000`
3. Terminal 2, di folder `backend`: `python -m tools.fake_publisher` (satu pesan per menit; tambah `--interval 5` untuk uji cepat)
4. Buka `http://localhost:8000/api/health` untuk memeriksa status, dan `http://localhost:8000/api/dashboard` untuk datanya.

Setelah ESP32 sungguhan dipakai, Mosquitto harus menerima koneksi dari jaringan (`listener 1883` di `mosquitto.conf`,
ditambah autentikasi). Atur ini bersama keputusan nomor 1 dan 3 di `docs/04-keputusan-terbuka.md`.

## Tes

```powershell
python -m pytest -q
```

## Struktur

| Berkas | Fungsi |
|---|---|
| `app/config.py` | Semua pengaturan dari environment variable (lihat `../.env.example`) |
| `app/ingest.py` | Validasi pesan, simpan, prediksi, rekomendasi |
| `app/predictor.py` | Persistence, demo linear, dan tempat memasang GRU (`GRUPredictor`) |
| `app/recommend.py` | Aturan rekomendasi (draf, bisa diubah) |
| `app/dashboard.py` | Menyusun JSON `/api/dashboard` sesuai `frontend/lib/types.ts` |
| `app/mqtt_client.py` | Subscribe sensor dan status, publish rekomendasi |
| `app/main.py` | Aplikasi FastAPI |
| `tools/` | `seed_db.py` (riwayat simulasi) dan `fake_publisher.py` (meniru ESP32) |
| `../database/schema.sql` | Skema SQLite |

## Endpoint

| Endpoint | Fungsi |
|---|---|
| `GET /api/dashboard` | Data untuk dashboard. 404 jika belum ada data valid |
| `GET /api/health` | Status MQTT, perangkat, pembacaan terakhir, dan `stale` |
| `GET /api/readings?from=&to=` | Pembacaan mentah (ISO 8601 UTC) |
| `GET /api/predictions?from=&to=` | Riwayat prediksi untuk evaluasi |

Dokumentasi interaktif: `http://localhost:8000/docs`.

## Memasang model GRU nanti

Isi `GRUPredictor` di `app/predictor.py` (muat model, siapkan jendela masukan, kembalikan 15 nilai), lalu set
`PREDICTOR=gru` dan `MODEL_PATH`. Bagian lain tidak perlu diubah. Sebelum itu, sepakati dengan `ml/`: panjang jendela,
fitur masukan, skala normalisasi, dan format berkas model.

## Catatan penting

- `tools/` menghasilkan **data simulasi**. Jangan dipakai sebagai data atau hasil TA.
- `linear-demo` hanya untuk tampilan dashboard. Bukan model TA. Nilai bawaan `persistence` sesuai dokumen arsitektur.
- Tambahkan ke `.gitignore` di root: `.env`, `.venv/`, `__pycache__/`, `backend/data/`.
