# Arsitektur Sistem CO₂ Classroom IoT

**Status dokumen:** 4 November 2026. Pisahkan komponen yang sudah diuji dari target arsitektur penelitian.

## 1. Tujuan

Memantau kondisi ruang GD525, membangun deret waktu kualitas udara, serta mengembangkan prediksi konsentrasi CO₂ horizon 15 menit menggunakan GRU untuk mendukung rekomendasi ventilasi lebih awal.

## 2. Arsitektur saat ini (telah diuji)

```text
┌──────────────────────────────┐
│ Ruang GD525                  │
│ ESP32 + MH-Z19C + DHT22 + PIR│
└──────────────┬───────────────┘
               │ JSON setiap ±10 detik
               │ Wi-Fi, MQTT/TLS (8883)
               ▼
┌──────────────────────────────┐
│ H200: Mosquitto              │
│ classroom/gd525/sensors      │
└──────────────┬───────────────┘
               │ subscribe
               ▼
┌──────────────────────────────┐
│ FastAPI + Paho MQTT          │
│ app/mqtt_client.py           │
│ app/ingest.py                │
├──────────────────────────────┤
│ SQLite                       │
│ sensor_reading               │
│ prediction                   │
│ recommendation               │
└──────────────────────────────┘
             ▲
             │ systemd menjaga proses aktif
             └── co2class-backend.service

SQLite ── SQLite Backup API ── backup harian (systemd timer)
```

Backend menggunakan baseline persistence; pengisian 15 horizon menghasilkan 15 baris tabel `prediction` per pembacaan valid dan 1 baris `recommendation`.

## 3. Target arsitektur penelitian (belum sepenuhnya diterapkan)

```text
Data mentah (10 detik)
    → validasi & deteksi gap
    → agregasi ke grid 1 menit
    → split kronologis train/val/test
    → baseline persistence vs GRU
    → prediksi CO₂ t+15 menit
    → aturan rekomendasi ventilasi
    → dashboard Next.js dan indikator LED ESP32
```

Tahap ML perlu menggunakan fitur CO₂, suhu, RH, dan indikator aktivitas PIR sesuai hasil eksperimen. PIR **tidak** mengukur jumlah penghuni. Kondisi pintu/jendela, presensi, dan jadwal kelas dapat dicatat manual sebagai metadata lapangan.

## 4. Spesifikasi perangkat dan koneksi

| Komponen | Koneksi/logika | Status |
|---|---|---|
| ESP32 DevKit1 | Wi-Fi kampus | Teruji |
| MH-Z19C UART | Sensor TX → GPIO26; sensor RX → GPIO25 | Teruji |
| DHT22 | Data → GPIO4 | Teruji |
| HC-SR501 | OUT → GPIO27 | Teruji |
| PIR motion latch | HIGH dalam periode pengiriman dicatat sebagai aktivitas | Diterapkan; bukan counter |
| LED status prediksi | Output rekomendasi server → ESP32 | Rencana/harus diuji |

Perhatikan kecocokan tegangan/catu daya dan ground bersama pada perakitan fisik. Pin ESP32 merupakan penamaan GPIO sebagaimana firmware yang dibagikan.

## 5. Kontrak MQTT

| Fungsi | Topik | Arah |
|---|---|---|
| Data sensor | `classroom/gd525/sensors` | ESP32 → broker → backend |
| Rekomendasi | `classroom/gd525/recommendation` | Backend → broker → ESP32, perlu uji end-to-end |
| Status perangkat | `classroom/<room_id>/status` | Perangkat → backend, jika dipublikasikan |

Contoh pesan sensor saat ini:

```json
{"co2": 1004, "temperature": 26.90, "humidity": 74.00, "pir": 1}
```

`app/ingest.py` menormalisasi nama field (`co2` menjadi `co2_ppm`, `temperature` menjadi `temp_in_c`, dan sebagainya). Payload firmware saat ini belum mengirim waktu pengukuran, device sequence, atau tanda kegagalan secara terstruktur. Timestamp penerimaan H200 menjadi acuan sementara.

## 6. Alur backend

1. `mqtt_client.py` melakukan TLS dan autentikasi ke Mosquitto, lalu subscribe data sensor.
2. `ingest.py` memvalidasi payload, mencatat quality flags dan menyimpan baris `sensor_reading`.
3. `predictor.py` menghasilkan forecast awal, saat ini persistence baseline.
4. `recommend.py` membuat keputusan berdasarkan ambang operasional penelitian.
5. Prediksi dan rekomendasi tersimpan di database; backend juga memiliki fungsi publikasi rekomendasi MQTT.
6. Dashboard mengambil data dari API sesuai endpoint yang tersedia; akses pengguna dan integrasi penuh masih perlu diverifikasi.

## 7. Desain deployment dan keamanan

- API FastAPI saat ini bind pada `127.0.0.1:8000`, tidak dibuka langsung ke jaringan kampus.
- MQTT menggunakan TLS di `172.22.44.29:8883` pada lingkungan kampus; IP tersebut spesifik deployment, bukan konfigurasi universal.
- Password MQTT disimpan di `.env` yang tidak ikut Git.
- Backend dijalankan sebagai service `co2class-backend.service` dengan `systemd`.
- Backup SQLite terjadwal menggunakan `co2class-backup.timer`, tetapi saat ini disimpan pada host yang sama.
- Jangan menjalankan dua instance backend dengan MQTT client ID sama.

## 8. Risiko dan batas yang perlu ditangani

| Risiko | Penanganan berikutnya |
|---|---|
| Restart ESP32 saat NTP tidak tersedia | Sumber waktu tepercaya dan kebijakan TLS yang benar |
| Kehilangan sampel akibat Wi-Fi/MQTT | Audit gap, sequence number, monitoring status; pertimbangkan buffering di perangkat |
| MQTT QoS 0 pada publish firmware | Tidak menjamin setiap sampel diterima; evaluasi QoS dan idempotensi |
| Backup hanya pada H200 | Retensi, validasi restore, dan salinan off-server |
| Dataset bercampur antara demo dan nyata | Pisahkan mode data dan catat provenance |
| Model belum GRU | Benchmark baseline kemudian pelatihan dan evaluasi GRU |

## 9. Referensi internal

- [README utama](../README.md)
- [Deployment H200](deployment-h200.md)
- [Pengumpulan data](data-collection.md)
- [Roadmap](development-roadmap.md)
