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

Data 10 detik **dipertahankan** untuk audit dan kini telah diuji bisa diubah menjadi grid **1 menit** lewat `ml/preprocessing/resample_sensor_data.py`. Preprocessing dijalankan **manual**, bukan layanan otomatis; output development tidak sama dengan dataset resmi GD525.

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

## 6. Preprocessing 1 menit — sudah diuji pada data development

Implementasi: `ml/preprocessing/resample_sensor_data.py`; pengujian di `ml/preprocessing/tests/` telah menghasilkan **2 unit test lulus**. Kode membaca SQLite secara read-only, membentuk grid UTC per menit, agregasi **rata-rata** CO₂/suhu/RH dan **maksimum** PIR. Menit lengkap yang memenuhi minimal **5 dari 6** sampel valid ditandai `usable`; status lain antara lain `incomplete`, `missing`, `boundary_partial`. Tersedia `n_received`, `n_valid`, `n_rejected`, `coverage_pct`.

Contoh jalankan dari root repository pada H200:

```bash
python3 -m unittest discover -s ml/preprocessing/tests -v
python3 ml/preprocessing/resample_sensor_data.py
```

Output default ke `ml/data/processed/development/`: `all_minutes.csv`, `usable_minutes.csv`, `resample_report.json`. **Tidak ada interpolasi otomatis.** Saat membangun sliding window GRU, validasi kontinuitas timestamp harus menggunakan grid lengkap, jangan menyambungkan baris `usable_minutes.csv` yang terpisah gap.

Hasil pengujian development tercatat: **456 raw rows → 78 menit, 73 usable, 3 incomplete, 2 boundary, 0 missing**, hanya untuk contoh kesiapan pipeline. Threshold 5/6 adalah pilihan engineering awal dan perlu dinilai ulang pada data penelitian.

### Audit development yang sudah dilakukan

- Awal audit: 359 baris, 0 NULL pada empat fitur, 0 timestamp duplikat dan invalid, 0 nilai di luar rentang.
- Interval rata-rata 10,34 detik; median 10 detik. Ditemukan enam gap >15 detik terkonsentrasi pada masa perpindahan backend manual ke systemd.
- Pada subset sesudah `2026-11-04T14:07:00Z`, **379 baris** memiliki interval 8–12 detik seluruhnya dan tanpa gap >15 detik.
- Seluruh 359 baris audit awal memiliki `ts_corrected` karena firmware tidak menyertakan timestamp; ini tidak membuktikan latensi jaringan nol.

Hasil audit singkat tidak membuktikan kestabilan selama 4 minggu atau validitas nilai sensor terhadap alat referensi.

### Penanganan gap untuk eksperimen

Usulan lama interpolasi linear pada gap 1–3 menit **belum diterapkan**; jangan menggunakan interpolasi tanpa justifikasi dan penanda `imputed`, terlebih jika dapat menyebabkan kebocoran data dari masa depan. Window yang melewati menit tidak usable harus ditolak atau ditangani oleh strategi yang didokumentasikan.

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

## 9. Pemasangan, kalibrasi, dan catatan manual

### Penempatan sensor (rencana, verifikasi lapangan)

| Komponen | Rekomendasi penempatan |
|---|---|
| MH-Z19C | Sekitar zona napas penghuni duduk (usulan 1–1,5 m), jauh dari embusan napas langsung, pintu/jendela dan ventilasi langsung |
| DHT22 dalam | Dekat pengukuran CO₂ tetapi jauh dari panas ESP32, laptop/proyektor dan matahari |
| PIR | Menghadap aktivitas tempat duduk, tidak terhalang; `0` bukan bukti ruangan kosong |
| ESP32/LED | Catu daya stabil dan lokasi aman, LED terlihat; dokumentasikan posisi |
| DHT22 luar | **Belum terpasang dalam sistem aktif**; jika ditambahkan harus terlindung hujan/panas matahari |

Jangan memindahkan alat selama periode resmi tanpa mencatat waktu/alasan perubahan. Dokumentasikan foto, sketsa dan tinggi pemasangan. Periksa warm-up MH-Z19C menurut datasheet dan catat periode yang dikecualikan. Tinjau pengaturan ABC (Automatic Baseline Correction) dan uji sanity check udara luar sebelum mengambil data resmi; kebijakan kalibrasi belum final.

### Event log manual, bukan input otomatis model

Catat peristiwa `kelas_mulai`, `kelas_selesai`, `jendela_buka`, `jendela_tutup`, `pintu_buka`, `pintu_tutup`, `flush_dilakukan`, `lainnya`. Struktur CSV yang diusulkan: `waktu_wib,jenis,jumlah_orang_perkiraan,catatan,pencatat`. Gunakan inisial, jangan nama mahasiswa; catat apakah log per hari lengkap. Data presensi/jadwal dan pintu/jendela adalah metadata untuk analisis, bukan fitur sensor otomatis.

## 10. Backup, akses, dan etika

Backup H200 sudah dikonfigurasi setiap hari **17:00 UTC = 00:00 WIB**, menggunakan SQLite Backup API. Namun, backup masih di host yang sama: diperlukan backup off-server, kebijakan retensi dan uji restore. Hindari merekam data identitas pribadi dalam pembacaan sensor. Catatan presensi/manual perlu dikelola sesuai kebijakan kampus dan tujuan penelitian.

## 11. Kriteria mulai periode pengumpulan resmi

- [ ] Firmware dapat berjalan melewati 15 menit dan melewati restart dengan clock tepercaya.
- [ ] ESP32 dipasang pada posisi dan catu daya yang stabil di ruang GD525.
- [ ] Konektivitas MQTT dan backend stabil dalam uji lebih panjang.
- [ ] Backup off-server dan restore diuji.
- [ ] Monitoring gap/ketiadaan data disiapkan.
- [ ] Prosedur metadata lapangan dan kalender pengambilan disepakati.
- [ ] Waktu mulai, versi firmware, dan hash commit repository dicatat.

## 12. Dokumen terkait

[Arsitektur](architecture.md) · [Deployment H200](deployment-h200.md) · [Roadmap](development-roadmap.md)

[Kontrak data](data-contract.md) · [Keputusan dan risiko](decisions-and-risks.md)
