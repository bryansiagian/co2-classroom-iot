# Kontrak Data — MQTT, Backend dan Dashboard

**Status: 4 November 2026 — kontrak aktif (ESP32 V4.1 + backend H200) dan rancangan evolusi dipisahkan.** Ini menggantikan `02-kontrak-data.md` yang mencampurkan rancangan per menit dengan sistem yang benar-benar sedang berjalan.

## 1. Konvensi

- Ruang `gd525`, CO₂ ppm, suhu °C, kelembapan relatif %RH, PIR `0/1` (aktivitas, **bukan** jumlah orang).
- Timestamp backend dan database UTC; WIB dipakai saat menampilkan kepada pengguna. REST API menampilkan timestamp berdasarkan bentuk endpoint; `GET /api/dashboard` menggunakan epoch milidetik untuk bagian dashboard.
- Jangan menganggap timestamp penerimaan sama dengan waktu sensor mengukur. Pencatatan awal menggunakan waktu penerimaan H200.

## 2. Topik MQTT yang aktif

| Topik | Arah | Catatan implementasi |
|---|---|---|
| `classroom/gd525/sensors` | ESP32 → Mosquitto → backend | Publish Arduino `PubSubClient.publish()` QoS 0; backend subscribe QoS 1, efektivitas pengiriman tetap QoS 0 |
| `classroom/gd525/recommendation` | backend → broker → ESP32 (direncanakan) | Kode backend menerbitkan QoS 1, retained; penerimaan/LED ESP32 **belum diuji** |
| `classroom/<room_id>/status` | ESP32 → backend (opsional/rencana) | Backend sudah subscribe; status/LWT firmware belum dibuktikan |

MQTT/TLS Mosquitto H200 memakai IP lingkungan uji `172.22.44.29`, port TCP `8883`, sertifikat publik dan autentikasi akun terpisah. Jangan menaruh password dalam dokumen.

### Payload sensor AKTIF (sekitar 10 detik)

```json
{"co2":1048,"temperature":26.70,"humidity":74.40,"pir":0}
```

| Field | Tipe | Pengertian |
|---|---|---|
| `co2` | integer | Konsentrasi CO₂ (ppm) dari MH-Z19C |
| `temperature` | number | Suhu dalam °C dari DHT22 |
| `humidity` | number | RH dalam % |
| `pir` | 0/1 | `1` bila latch gerakan mendeteksi HIGH sejak pengiriman sebelumnya |

Firmware V4.1 **belum** mengirim `ts`, `seq`, `device_id`, `faults`, `rssi`, atau sensor DHT22 luar. Jika pembacaan wajib gagal, firmware melewati pengiriman saat itu. Di `app/ingest.py`, bentuk ringkas ini dipetakan menjadi `co2_ppm`, `temp_in_c`, `hum_in_pct`, `pir`, `device_id=esp32_gd525`, `ts=None`, `faults=[]`. Backend memberi `quality_flags=["ts_corrected"]` karena timestamp perangkat tidak ada. Rentang validasi backend: CO₂ 350–5000, suhu -10–60 °C, RH 0–100%; nilai mencurigakan ditandai `suspect`.

### Format kaya — RANCANGAN LAMA, belum kontrak firmware aktif

```json
{
  "v":1,"device_id":"esp32-gd525-01","seq":1234,
  "ts":"2026-10-19T04:30:00Z", "co2_ppm":812,
  "temp_in_c":27.9,"hum_in_pct":62.3,
  "temp_out_c":null,"hum_out_pct":null,
  "pir":1,"rssi":-61,"faults":[]
}
```

Rencana ini berguna untuk mendeteksi reset, pesan hilang/duplikat dan sensor gagal secara parsial. **Jangan mengganti topik aktif atau format payload tanpa perubahan serentak firmware, ACL broker, backend, pengujian dan dokumentasi.** Topik lama `co2class/gd525/sensor` adalah rancangan terdahulu, **bukan** topik aktif.

## 3. Rekomendasi ventilasi

Backend menyimpan satu baris `recommendation` per pembacaan valid dan bisa menerbitkan payload berikut (contoh format, bukan bukti LED sudah menerima):

```json
{
  "v":1,"ts":"2026-11-04T14:07:00Z", "action":"flush",
  "minutes":4,"predicted_peak_ppm":1180,
  "predicted_at_15min_ppm":1165,"model":"persistence"
}
```

Aturan fungsi `app/recommend.py` pada baseline saat ini menggunakan maksimum prediksi 15 horizon:

| Predicted peak | Action | Minutes |
|---|---|---:|
| `<800 ppm` | `none` | 0 |
| `800–999 ppm` | `watch` | 0 |
| `1000–1149 ppm` | `flush` | 3 |
| `1150–1499 ppm` | `flush` | 4 |
| `≥1500 ppm` | `flush` | 5 |

Ambang 800/1000/1500 berasal dari konfigurasi backend, sedangkan batas 1150 dan durasi 3–5 menit saat ini adalah logika kode/draf yang masih memerlukan dasar dan evaluasi ilmiah. LED hijau/kuning/merah sesuai `none/watch/flush` adalah **rancangan**, bukan integrasi yang sudah terbukti.

## 4. REST API backend

Implementasi dalam `backend/backend/app/main.py`:

| Endpoint | Status kode | Fungsi |
|---|---|---|
| `GET /api/dashboard` | Ada | DTO dashboard; 404 jika belum ada pembacaan valid |
| `GET /api/health` | Ada | MQTT connected, staleness, predictor, sensor terakhir |
| `GET /api/readings?from=<ISO8601>&to=<ISO8601>` | Ada | Pembacaan sensor dalam rentang UTC; limit default 5000, maks 20000 |
| `GET /api/predictions?from=<ISO8601>&to=<ISO8601>` | Ada | Prediksi beserta waktu target dan horizon |

Keberadaan endpoint di kode **tidak berarti dashboard Next.js telah diuji end-to-end**. `GET /api/dashboard` mengikuti `frontend/lib/types.ts`; contoh skema konseptual:

```json
{
  "room":"GD 525","updatedAt":1792384200000,
  "current":{"co2":812,"tempIn":27.9,"humIn":62.0,"tempOut":null,"humOut":null,"occupied":true},
  "history":[{"t":1792384140000,"co2":805}],
  "forecast":[{"t":1792384260000,"co2":820}],
  "recommendation":{"action":"watch","minutes":0,"reason":"Perhatikan tren CO₂."},
  "events":[{"t":1792383000000,"text":"CO₂ melewati 800 ppm","level":"watch"}]
}
```

Contoh di atas **ilustratif**; untuk field, batas jumlah titik, dan nullabilitas yang pasti, gunakan `app/dashboard.py` dan `frontend/lib/types.ts` pada commit yang sedang di-deploy. Rancangan historis mengusulkan `history` maksimal 360 titik/6 jam, `forecast` 15 titik, `events` maksimal 5, serta occupancy dari PIR 5 menit terakhir: verifikasi sebelum menganggapnya kontrak aktif.

## 5. Pemetaan database

| Tabel | Fungsi |
|---|---|
| `sensor_reading` | `ts_utc`, `received_at`, nilai sensor, `faults`, `quality_flags`, `raw` dan identitas ruang/perangkat |
| `prediction` | 15 baris per prediksi valid pada baseline (t+1 hingga t+15 menit), `model`, `target_ts` |
| `recommendation` | `action`, durasi, peak, nilai t+15, model |
| `manual_event` | Catatan pintu/jendela/kelas bila tersedia dalam schema; integrasi input manual belum diuji |

Skema aktual adalah `backend/database/schema.sql`. **Jangan tertukar** dengan tabel `sensor_readings` (plural) di `~/gd525-iot-test/gd525_test.db` dari collector percobaan lama.

## 6. Evolusi kontrak sebelum deployment GD525

1. Tetapkan kebijakan `seq`, timestamp perangkat tepercaya dan `faults`; uji kompatibilitas dengan backend.
2. Tentukan QoS, deduplikasi dan buffer offline. Saat ini MQTT QoS 0 belum menjamin tidak ada sampel yang hilang.
3. Uji publish rekomendasi, subscribe ESP32, LED, Last Will, dan status stale.
4. Versikan kontrak serta catat versi firmware/model sebelum penelitian resmi.

Lihat [arsitektur](architecture.md), [pengambilan data](data-collection.md), [risiko](decisions-and-risks.md).
