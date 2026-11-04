# Protokol Pengumpulan Data Sensor GD525

**Status:** rancangan metode serta hasil validasi awal per 4 November 2026. **Belum** menjadi laporan hasil pengumpulan resmi selama 4 minggu.

## 1. Tujuan dan cakupan

Menghasilkan deret waktu untuk evaluasi model GRU yang memprediksi konsentrasi CO₂ **15 menit ke depan**. Pengambilan data berfokus pada **satu ruang kelas, GD525**, dengan target sedikitnya **4 minggu** agar ada variasi jam pelajaran, hari, dan kondisi ventilasi.

## 2. Perangkat dan variabel

| Variabel | Sumber | Satuan/tipe | Catatan |
|---|---|---|---|
| CO₂ | MH-Z19C NDIR | ppm | Target prediksi |
| Suhu | DHT22 | °C | Potensi dipengaruhi lokasi alat/panas perangkat |
| Kelembapan relatif | DHT22 | %RH | Periksa rentang 0–100 |
| Aktivitas PIR | HC-SR501 | 0/1 | Gerakan selama interval, **bukan** jumlah orang |
| Waktu penerimaan | Server H200 | UTC | Acuan saat firmware belum mengirim timestamp tepercaya |

Metadata manual yang dianjurkan: jadwal kelas, perkiraan/rekap presensi, kondisi pintu dan jendela, kejadian khusus, posisi sensor, pemadaman dan gangguan jaringan. Metadata ini tidak otomatis menjadi input model GRU.

## 3. Jalur dan frekuensi sampling

ESP32 V4.1 mengirim payload JSON kira-kira setiap **10 detik** ke topik `classroom/gd525/sensors` menggunakan MQTT/TLS. Backend FastAPI menyimpan pembacaan mentah ke tabel `sensor_reading` pada SQLite H200.

Data 10 detik **dipertahankan** untuk audit dan dapat diubah menjadi grid **1 menit** di tahap preprocessing. Jangan menganggap file CSV atau tabel 1 menit telah otomatis dibuat saat ini.

Contoh payload:

```json
{"co2": 1048, "temperature": 26.7, "humidity": 74.4, "pir": 0}
```

Firmware V4.1 belum mengirim `ts`, `device_id`, atau `seq` eksplisit; pipeline backend mengisi waktu penerimaan server dan dapat memberi flag `ts_corrected`. Dengan MQTT QoS 0 pada sisi publish firmware, sampel bisa hilang saat jaringan bermasalah. Jangan melakukan interpolasi tanpa mencatat gap.

## 4. Penyimpanan dan provenance

- Database backend: `backend/backend/data/co2class.db` (lokasi lingkungan server H200).
- Tabel sensor: `sensor_reading` (singular), **berbeda** dari tabel `sensor_readings` pada collector pengujian lama.
- Tabel hasil sementara: `prediction` dan `recommendation`.
- Prediksi awal yang sedang berjalan adalah **persistence baseline**, bukan GRU.
- Database pengujian lama `~/gd525-iot-test/gd525_test.db` tidak boleh diam-diam digabung dengan dataset resmi.
- Data sintetis/demo harus dilabeli dan dipisah dari data nyata.
- Simpan log versi firmware, versi kode, konfigurasi interval, dan tanggal perubahan perangkat.

## 5. Aturan pemeriksaan kualitas data

Minimal audit harian/berkala:

1. **Kelengkapan:** hitung data per jam/hari dibanding ekspektasi kira-kira 360 sampel/jam jika 10 detik stabil; ini tolok ukur, bukan batas mutlak.
2. **Gap:** hitung selisih timestamp penerimaan berturut-turut; soroti interval jauh dari 10 detik, misalnya lebih dari 20 detik.
3. **Missing dan invalid:** jumlah `NULL`, flags `suspect`, nilai di luar jangkauan kerja.
4. **Duplikasi:** identifikasi timestamp sama atau pembacaan ganda; tanpa sequence ID, deduplikasi sempurna tidak dijamin.
5. **Konsistensi waktu:** UTC server, clock drift, restart firmware, perubahan jam, dan peristiwa sinkronisasi.
6. **Drift sensor:** cek perubahan ekstrem, rentang CO₂, efek pemanasan DHT22 atau lokasi dekat perangkat panas.
7. **Ketersediaan sistem:** catat restart backend, downtime MQTT, kegagalan suplai daya dan Wi-Fi.

Validasi ingest yang diketahui mencatat flag `suspect` jika CO₂ di luar 350–5000 ppm, suhu di luar -10–60 °C, atau RH di luar 0–100%; keputusan final untuk membuang/menandai sampel perlu dijelaskan pada protokol eksperimen.

## 6. Rencana preprocessing 1 menit

**Belum diimplementasikan sebagai hasil dataset resmi.** Rencana yang disarankan:

1. Urutkan berdasarkan timestamp UTC penerimaan yang tervalidasi dan identitas ruang.
2. Bentuk grid 1 menit tetap, tanpa menggunakan informasi dari masa depan.
3. Agregasi CO₂, suhu, RH dengan statistik yang ditentukan sebelumnya (misalnya median dalam 1 menit), dan PIR dengan `max` (ada/tidak ada gerakan).
4. Catat jumlah sampel mentah per menit (`sample_count`) serta indikator gap/kelengkapan.
5. Tandai menit kosong sebagai missing; tetapkan aturan imputasi hanya pada data train, kemudian terapkan tanpa leakage ke validation/test.
6. Simpan output terpisah dan ber-versi; jangan menimpa raw sensor readings.

Bila PIR sensor tetap HIGH sekitar puluhan detik setelah pemicuan, agregasi PIR perlu diperlakukan sebagai indikator aktivitas kasar, bukan okupansi atau jumlah gerakan aktual.

## 7. Skema eksperimen GRU

- **Target utama:** CO₂ pada t+15 menit.
- **Input awal:** CO₂, suhu, RH, PIR pada sejarah waktu tertentu; panjang lookback dievaluasi.
- **Baseline:** persistence (nilai terakhir) wajib dibandingkan dengan GRU.
- **Split:** kronologis, target awal train 70%, validasi 15%, test 15%; tidak mengacak data waktu.
- **Metrik regresi:** MAE, RMSE, R² bila sesuai dan dijelaskan.
- **Metrik rekomendasi:** precision, recall, F1/confusion matrix untuk peristiwa melewati ambang, dan lead time.
- **Hindari leakage:** normalisasi, imputasi, dan tuning hanya menggunakan rentang train/validation, bukan test.

## 8. Ambang rekomendasi operasional (untuk dievaluasi)

| Konsentrasi | Status rancangan |
|---|---|
| `<800 ppm` | Aman |
| `800–999 ppm` | Waspada |
| `≥1000 ppm` | Rekomendasi membuka ventilasi |
| `≥1500 ppm` | Kritis |

Ambang adalah pilihan operasional proyek dan harus diuji pada konteks ruang kelas; tidak otomatis merupakan ketentuan hukum atau ukuran keselamatan yang universal. Evaluasi juga perlu mencatat alarm palsu, keterlambatan, dan kemungkinan penggunaan hysteresis.

## 9. Backup, akses, dan etika

Backup H200 sudah dikonfigurasi setiap hari **17:00 UTC = 00:00 WIB**, menggunakan SQLite Backup API. Namun, backup masih di host yang sama: diperlukan backup off-server, kebijakan retensi dan uji restore. Hindari merekam data identitas pribadi dalam pembacaan sensor. Catatan presensi/manual perlu dikelola sesuai kebijakan kampus dan tujuan penelitian.

## 10. Kriteria mulai periode pengumpulan resmi

- [ ] Firmware dapat berjalan melewati 15 menit dan melewati restart dengan clock tepercaya.
- [ ] ESP32 dipasang pada posisi dan catu daya yang stabil di ruang GD525.
- [ ] Konektivitas MQTT dan backend stabil dalam uji lebih panjang.
- [ ] Backup off-server dan restore diuji.
- [ ] Monitoring gap/ketiadaan data disiapkan.
- [ ] Prosedur metadata lapangan dan kalender pengambilan disepakati.
- [ ] Waktu mulai, versi firmware, dan hash commit repository dicatat.

## 11. Dokumen terkait

[Arsitektur](architecture.md) · [Deployment H200](deployment-h200.md) · [Roadmap](development-roadmap.md)
