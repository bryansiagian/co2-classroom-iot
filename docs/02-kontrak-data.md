# 02. Kontrak Data

Dokumen ini adalah sumber kebenaran untuk format data antar komponen. Versi kontrak: **1**.

## Konvensi umum

- Waktu di MQTT dan database: ISO 8601 UTC, contoh `2026-10-19T04:30:00Z`.
- Waktu di REST API untuk dashboard: epoch milidetik (sesuai `frontend/lib/types.ts`).
- Tampilan ke pengguna memakai WIB (Asia/Jakarta).
- Satuan: CO₂ dalam ppm, suhu dalam °C, kelembapan dalam persen RH.
- Pembulatan: CO₂ bilangan bulat, suhu dan kelembapan satu desimal.
- Identitas: `device_id` dan `room_id` bersifat tetap, contoh `esp32-gd525-01` dan `gd525`.

## 1. Topik MQTT

Awalan topik: `co2class/{room_id}/`, contoh `co2class/gd525/`.

| Topik | Arah | QoS | Retained | Isi |
|---|---|---|---|---|
| `co2class/gd525/sensor` | ESP32 ke backend | 1 | tidak | Pembacaan sensor per menit |
| `co2class/gd525/status` | ESP32 ke backend | 1 | ya | `online` atau `offline` (offline lewat Last Will) |
| `co2class/gd525/recommendation` | backend ke ESP32 | 1 | ya | Rekomendasi terbaru untuk LED |

## 2. Pesan sensor (`.../sensor`)

```json
{
  "v": 1,
  "device_id": "esp32-gd525-01",
  "seq": 1234,
  "ts": "2026-10-19T04:30:00Z",
  "co2_ppm": 812,
  "temp_in_c": 27.9,
  "hum_in_pct": 62.3,
  "temp_out_c": 24.8,
  "hum_out_pct": 78.1,
  "pir": 1,
  "rssi": -61,
  "faults": []
}
```

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `v` | integer | ya | Versi kontrak |
| `device_id` | string | ya | Identitas perangkat |
| `seq` | integer | ya | Nomor urut naik per pesan. Dipakai backend untuk mendeteksi pesan hilang atau ganda. Kembali ke 0 saat ESP32 restart |
| `ts` | string | tidak | Waktu dari NTP. Jika NTP belum sinkron, kosongkan. Backend memakai waktu terima dan menandainya |
| `co2_ppm` | integer atau null | ya | Rata-rata satu menit dari pembacaan MH-Z19C |
| `temp_in_c`, `hum_in_pct` | number atau null | ya | DHT22 dalam ruangan |
| `temp_out_c`, `hum_out_pct` | number atau null | ya | DHT22 luar ruangan |
| `pir` | 0 atau 1 | ya | 1 jika ada gerakan terdeteksi pada menit tersebut |
| `rssi` | integer | tidak | Kekuatan sinyal Wi-Fi (dBm), untuk diagnosis |
| `faults` | array string | ya | Daftar sensor yang gagal, nilai yang mungkin: `co2`, `dht_in`, `dht_out`, `pir`. Kosong jika normal |

Aturan validasi di backend (pesan tetap disimpan mentah, nilai yang tidak valid ditandai, tidak dibuang):

| Field | Rentang valid | Jika di luar rentang |
|---|---|---|
| `co2_ppm` | 350 sampai 5000 | Tandai `suspect` |
| `temp_*_c` | -10 sampai 60 | Tandai `suspect` |
| `hum_*_pct` | 0 sampai 100 | Tandai `suspect` |
| `ts` | tidak lebih dari 5 menit dari waktu terima | Pakai waktu terima, tandai `ts_corrected` |

## 3. Pesan rekomendasi (`.../recommendation`)

```json
{
  "v": 1,
  "ts": "2026-10-19T04:30:05Z",
  "action": "flush",
  "minutes": 4,
  "predicted_peak_ppm": 1080,
  "predicted_at_15min_ppm": 1060,
  "model": "gru-v1"
}
```

| Field | Keterangan |
|---|---|
| `action` | `none`, `watch`, atau `flush` |
| `minutes` | Lama ventilasi yang disarankan, 0 jika bukan `flush` |
| `predicted_peak_ppm` | Nilai tertinggi dari 15 prediksi ke depan |
| `predicted_at_15min_ppm` | Prediksi pada t+15 menit |
| `model` | Nama model, atau `persistence` jika memakai cadangan |

Pemetaan LED: `none` hijau, `watch` kuning, `flush` merah.

## 4. Aturan rekomendasi (draf, perlu disepakati)

Berdasarkan nilai tertinggi prediksi 15 menit ke depan (`peak`):

| Kondisi | `action` | `minutes` |
|---|---|---|
| `peak` kurang dari 800 | `none` | 0 |
| 800 sampai kurang dari 1000 | `watch` | 0 |
| 1000 sampai kurang dari 1150 | `flush` | 3 |
| 1150 sampai kurang dari 1500 | `flush` | 4 |
| 1500 atau lebih | `flush` | 5 |

Ambang utama 1000 ppm. Ambang 800 dan 1500 ppm dipakai untuk analisis sensitivitas dan harus bisa diubah lewat konfigurasi, bukan ditulis permanen di kode. Pembagian lama flush di atas adalah usulan awal dalam rentang 3 sampai 5 menit dari proposal. Ganti jika ada dasar yang lebih kuat.

## 5. REST API untuk dashboard

`GET /api/dashboard` mengembalikan satu objek. Bentuknya harus sama dengan `Dashboard` di `frontend/lib/types.ts`.

```json
{
  "room": "GD 525",
  "updatedAt": 1792384200000,
  "current": {
    "co2": 812, "tempIn": 27.9, "humIn": 62,
    "tempOut": 24.8, "humOut": 78, "occupied": true
  },
  "history":  [{ "t": 1792384140000, "co2": 805 }],
  "forecast": [{ "t": 1792384260000, "co2": 820 }],
  "recommendation": {
    "action": "watch", "minutes": 0,
    "reason": "CO₂ diprediksi naik ke 960 ppm. Belum perlu ventilasi."
  },
  "events": [{ "t": 1792383000000, "text": "CO₂ melewati 800 ppm", "level": "watch" }]
}
```

| Field | Keterangan |
|---|---|
| `history` | Pembacaan 1 menit sekali, urut naik, sampai 360 titik (6 jam terakhir) |
| `forecast` | Tepat 15 titik: t+1 sampai t+15 menit |
| `current.occupied` | `true` jika ada `pir` = 1 pada 5 menit terakhir |
| `events[].level` | `good`, `watch`, `high`, atau `critical` |
| `events` | Sampai 5 kejadian terbaru, terbaru di indeks 0 |

Endpoint tambahan (belum dibutuhkan frontend, ditulis agar backend tidak berubah arah nanti):

| Endpoint | Fungsi |
|---|---|
| `GET /api/health` | Status backend, broker, dan waktu pesan sensor terakhir |
| `GET /api/readings?from=&to=` | Pembacaan mentah untuk ekspor dan analisis |
| `GET /api/predictions?from=&to=` | Riwayat prediksi untuk evaluasi vs nilai aktual |

CORS harus mengizinkan origin dashboard (`http://localhost:3000` saat pengembangan).

## 6. Pemetaan ke tabel database (ringkas)

Skema lengkap ada di `database/`. Pemetaan awal:

| Tabel | Isi | Sumber |
|---|---|---|
| `sensor_reading` | Satu baris per pesan sensor: semua field, `received_at`, `quality_flags` | `.../sensor` |
| `prediction` | Satu baris per prediksi: waktu dibuat, waktu target (t+1 sampai t+15), nilai, `model` | Layanan prediksi |
| `recommendation` | Satu baris per rekomendasi: `action`, `minutes`, `predicted_peak_ppm`, `model` | Layanan prediksi |
| `manual_event` | Catatan manual (buka jendela, mulai kelas, dll.) | Impor dari catatan manual |

Prediksi disimpan terpisah dari pembacaan supaya evaluasi prediksi vs nilai aktual bisa dilakukan belakangan dengan menggabungkan berdasarkan waktu target.
