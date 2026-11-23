# Laporan Audit Kualitas Data Sensor GD 525

**Kode pekerjaan:** DE-02 (audit kualitas data)  
**Tanggal audit:** 23 November 2026  
**Ruang:** GD 525 (`room_id=gd525`)  
**Perangkat:** `esp32_gd525`  
**Sumber:** Snapshot SQLite `backend/backend/data/co2class_snapshot.db`, tabel `sensor_reading`  
**Cakupan:** 118.829 pembacaan sensor pada snapshot lokal (bukan database H200 yang terus bertambah)  
**Status:** Audit pemeriksaan awal selesai; terdapat keterbatasan timestamp dan beberapa pemeriksaan lanjutan.

> **Batasan penggunaan:** Hasil ini merupakan audit snapshot untuk pengembangan pipeline dan model. Status sebagai dataset final penelitian harus ditetapkan setelah pengumpulan, verifikasi kondisi lapangan, dan audit ulang pada snapshot final. Semua waktu pada laporan menggunakan UTC kecuali dinyatakan lain.

## 1. Tujuan dan metode

Audit ini menilai kelengkapan, identitas perangkat, duplikasi, flag/fault sensor, interval pengiriman, gap, timestamp, serta urutan pesan. Pemeriksaan dilakukan dengan kueri SQLite *read-only* dan analisis Python terhadap waktu `received_at`. Tidak ada record yang dihapus atau dimodifikasi.

Pemeriksaan dibagi menjadi:
- **DE-02A:** identitas perangkat dan duplikasi timestamp/pesan.
- **DE-02B:** missing values, `quality_flags`, `faults`, dan rentang dasar sensor.
- **DE-02C:** interval pengiriman dan gap.
- **DE-02D:** kesesuaian timestamp, urutan `seq`, dan sesi `boot_id`.

## 2. Identitas dan periode data

| Atribut | Hasil |
|---|---|
| Tabel | `sensor_reading` |
| Device ID | `esp32_gd525` (118.829 record) |
| Room ID | `gd525` (118.829 record) |
| Data pertama, UTC | 2026-11-04 14:03:01 |
| Data terakhir, UTC | 2026-11-23 02:16:51 |
| Rentang waktu | sekitar 18 hari 12 jam 13 menit 50 detik (18,51 hari) |
| Jumlah record | 118.829 |
| Median selang penerimaan | 10 detik |

Rentang kalender di atas **bukan** jumlah hari dengan data lengkap 24 jam. Data kosong pada sejumlah periode panjang.

### Struktur kolom yang tersedia

`id`, `room_id`, `device_id`, `seq`, `ts_utc`, `received_at`, `co2_ppm`, `temp_in_c`, `hum_in_pct`, `temp_out_c`, `hum_out_pct`, `pir`, `rssi`, `faults`, `quality_flags`, `raw`, `boot_id`, `uptime_ms`, dan `measured_at_utc`.

## 3. DE-02A — Audit duplikasi dan identitas

| Pemeriksaan | Hasil |
|---|---:|
| Timestamp `received_at` kosong | 0 |
| Nilai timestamp `received_at` yang muncul lebih dari sekali | 10 |
| Total record di kelompok timestamp berulang | 24 |
| Record tambahan di atas satu record per timestamp | 14 |
| Pengulangan kombinasi `boot_id + seq`, pada record yang kedua kolomnya terisi | 0 |
| Record tanpa `boot_id` | 1.533 |
| Record tanpa `seq` | 1.533 |

Pada beberapa timestamp yang sama, nilai CO₂/suhu/kelembapan berbeda. Contohnya, 8 November 2026 pukul 04:46:16 UTC memiliki empat pembacaan dengan `seq` 83–86 dan nilai CO₂ 1.843, 1.805, 1.914, dan 1.940 ppm. Keempatnya **tidak boleh langsung disebut duplikat identik**. Nilai `seq` berbeda dan berurutan, sehingga kemungkinan terdapat beberapa pesan berbeda yang dicatat pada detik yang sama.

**Keputusan audit:** Tidak ada dasar yang cukup untuk menghapus 14 record tersebut. Ketiadaan `boot_id`/`seq` pada 1.533 record awal membuat audit identitas pesan pada periode itu belum lengkap. Timestamp penerimaan sama saja tidak membuktikan retransmisi.

## 4. DE-02B — Kelengkapan dan kualitas pembacaan

### 4.1 Missing values

| Kolom | Nilai kosong | Proporsi dari 118.829 |
|---|---:|---:|
| `co2_ppm` | 0 | 0% |
| `temp_in_c` | 1.002 | sekitar 0,84% |
| `hum_in_pct` | 1.002 | sekitar 0,84% |
| `pir` | 0 | 0% |
| `faults` | 0 | 0% |
| `quality_flags` | 0 | 0% |
| `boot_id` | 1.533 | sekitar 1,29% |
| `seq` | 1.533 | sekitar 1,29% |
| `measured_at_utc` | 118.829 | 100% |

### 4.2 Fault dan quality flags

| Nilai `faults` | Record |
|---|---:|
| `[]` | 117.827 |
| `["temperature", "humidity"]` | 1.002 |

| Nilai `quality_flags` | Record |
|---|---:|
| `["ts_corrected"]` | 118.828 |
| `["suspect", "ts_corrected"]` | 1 |

Hasil audit menunjukkan bahwa 1.002 record gagal menghasilkan nilai suhu dan kelembapan, tetapi kolom CO₂ tetap terisi. Hal ini **tidak otomatis menjamin validitas CO₂**; validitasnya masih bergantung pada pemeriksaan rentang, flag, dan fault lain.

Pemeriksaan rentang dasar berikut menghasilkan **0 kasus**:
- CO₂ bernilai negatif;
- suhu di bawah −40 °C atau di atas 80 °C;
- kelembapan di bawah 0% atau di atas 100%;
- PIR di luar nilai 0 dan 1.

Rentang dasar audit bukan satu-satunya validasi pada pipeline: resampler menerapkan batas operasional CO₂ **350–5.000 ppm**, suhu **−10 hingga 60 °C**, kelembapan **0–100%**, dan PIR **0/1**. Nilai CO₂ yang tinggi tidak boleh dihapus semata-mata karena tinggi; perlu ditinjau bersama konteks dan kualitas sensor.

### 4.3 Implikasi terhadap dua profil dataset

- **Multivariate:** record dengan fault apa pun atau flag `suspect` ditolak oleh validator yang digunakan, karena fitur CO₂, suhu, kelembapan, dan PIR harus lengkap.
- **CO₂-only:** record dengan hanya fault `temperature`/`humidity` boleh digunakan jika CO₂ memenuhi validasi dan tidak memiliki flag `suspect`. Fitur non-CO₂ dibiarkan kosong pada keluaran profil ini.
- Flag `ts_corrected` dicatat, tetapi tidak otomatis menjadi alasan penolakan.

## 5. DE-02C — Interval pengiriman dan gap

| Pemeriksaan | Hasil |
|---|---:|
| Jumlah interval antar-record | 118.828 |
| Median interval | 10 detik |
| Interval tepat 10 detik | 116.834 (sekitar 98,32%) |
| Interval 0 detik | 14 |
| Interval lebih dari 30 detik | 37 |
| Interval lebih dari 60 detik | 14 |
| Interval lebih dari 5 menit | 12 |
| Interval lebih dari 1 jam | 7 |

Mayoritas interval tepat 10 detik. Namun, interval 0 detik dan gap panjang menunjukkan bahwa waktu penerimaan tidak selalu mencerminkan ritme pengukuran sensor.

### Sepuluh gap terpanjang (berdasarkan `received_at`)

| No. | Dari (UTC) | Sampai (UTC) | Durasi (menit) |
|---:|---|---|---:|
| 1 | 2026-11-08 05:52:44 | 2026-11-09 10:58:37 | 1.745,9 |
| 2 | 2026-11-04 15:29:03 | 2026-11-05 13:41:17 | 1.332,2 |
| 3 | 2026-11-06 17:06:37 | 2026-11-07 14:35:57 | 1.289,3 |
| 4 | 2026-11-05 13:49:49 | 2026-11-06 08:38:52 | 1.129,0 |
| 5 | 2026-11-07 16:28:01 | 2026-11-08 04:46:16 | 738,2 |
| 6 | 2026-11-06 08:46:45 | 2026-11-06 15:58:06 | 431,4 |
| 7 | 2026-11-21 15:24:30 | 2026-11-21 16:26:37 | 62,1 |
| 8 | 2026-11-13 01:38:45 | 2026-11-13 01:55:10 | 16,4 |
| 9 | 2026-11-06 15:58:19 | 2026-11-06 16:13:56 | 15,6 |
| 10 | 2026-11-11 14:21:49 | 2026-11-11 14:31:01 | 9,2 |

Enam dari tujuh gap di atas satu jam terjadi pada 4–9 November. Ada satu gap lebih dari satu jam pada 21 November. Audit ini **belum dapat memastikan** apakah gap disebabkan oleh daya, Wi-Fi, MQTT, restart, atau penghentian pengukuran yang disengaja.

## 6. DE-02D — Timestamp, sequence, dan sesi boot

| Pemeriksaan | Hasil |
|---|---:|
| `ts_utc = received_at` | 118.829 record |
| `ts_utc` berbeda dari `received_at` | 0 |
| `measured_at_utc` tersedia | 0 |
| Record dengan `boot_id` dan `seq` tersedia | 117.296 |
| `seq` berulang secara berurutan dalam `boot_id` | 0 |
| `seq` menurun dalam `boot_id` | 0 |
| Lompatan `seq` dalam `boot_id` | 31 |
| Jumlah `boot_id` berbeda | 3 |

Seluruh record memiliki flag `ts_corrected`, dan `ts_utc` identik dengan `received_at`. Dengan demikian, timestamp efektif yang tersedia untuk preprocessing adalah **waktu penerimaan backend**, bukan waktu pengukuran independen yang terverifikasi di ESP32.

Terdapat 31 peristiwa lompatan sequence, tetapi **angka tersebut bukan jumlah pasti pesan yang hilang**. Ukuran lompatan, penyebab, dan perilaku firmware saat mengirim ulang perlu diperiksa terpisah. Tiga `boot_id` yang berbeda mengindikasikan sedikitnya tiga identitas sesi boot yang tercatat, bukan jumlah pasti seluruh restart, karena record awal tidak memiliki metadata tersebut.

**Risiko yang perlu dicatat:** Jika pesan tertunda lalu diterima bersamaan, agregasi berdasarkan `received_at` dapat menempatkan pembacaan pada menit penerimaan, bukan menit pengukuran sebenarnya. Seluruh flag `ts_corrected` perlu dijelaskan menggunakan logika firmware/backend dan, jika tersedia, log koneksi.

## 7. Dampak terhadap preprocessing dan training GRU

Pipeline yang telah dibuat pada repository:

1. **`ml/preprocessing/resample_sensor_data.py`** membaca SQLite secara *read-only* dengan filter `room_id` dan `device_id`; mengelompokkan `received_at` ke menit UTC; memeriksa flag, fault, tipe/rentang sensor; dan menghasilkan `all_minutes.csv`, `usable_minutes.csv`, serta `resample_report.json`. Konfigurasi default menargetkan **6 sampel/menit** dan mensyaratkan sedikitnya **5 sampel valid/menit**. Menit batas awal/akhir ditandai `boundary_partial`.
2. **`ml/preprocessing/build_windows.py`** mensyaratkan seluruh menit dari input hingga target berstatus `usable` dan berurutan tepat satu menit. Tidak dilakukan interpolasi untuk menjembatani gap.
3. **`ml/training/train_gru.py`** membagi waktu secara kronologis sebelum membentuk window, melarang window melintasi batas split, dan menghitung parameter standardisasi hanya dari data training. Eksperimen saat ini memakai **lookback 60 menit** dan **horizon 15 menit**.

Untuk snapshot ini, laporan preprocessing sebelumnya menghasilkan:

| Ringkasan | Multivariate | CO₂-only |
|---|---:|---:|
| Menit usable | 19.818 | 19.836 |
| Menit incomplete | 60 | 42 |
| Menit missing | 6.774 | 6.774 |
| Segmen kontinu usable | 49 | 31 |
| Panjang segmen terpanjang (menit) | 3.749 | 12.079 |
| Window valid (60→15 menit) | 17.370 | 18.566 |

Angka preprocessing ini berasal dari keluaran pengujian sebelumnya pada snapshot yang sama; **bukan dihitung ulang oleh kueri audit DE-02A–D**. Periksa ulang terhadap `resample_report.json` dan `windows_report.json` saat finalisasi.

**Kesimpulan untuk model:** Tidak perlu menghapus seluruh data yang memiliki timestamp sama atau melakukan interpolasi gap panjang. Tetapi model yang memprediksi perubahan CO₂ perlu mempertimbangkan keterbatasan akurasi waktu pengukuran. Keputusan hasil evaluasi model harus didasarkan pada data dan metode pengujian yang terdokumentasi, bukan hanya banyaknya record.

## 8. Kesimpulan dan pekerjaan lanjutan

**Temuan utama:**
- Identitas perangkat/ruangan konsisten; tidak ada `received_at`, CO₂, atau PIR kosong pada snapshot.
- Sebanyak 1.002 record memiliki fault suhu dan kelembapan, sehingga tidak sesuai untuk fitur multivariat lengkap; nilai CO₂-nya dapat dinilai terpisah.
- Median pengiriman 10 detik dan sekitar 98,32% interval tepat 10 detik; tetap ada gap panjang.
- Ditemukan 10 timestamp berulang (24 record, 14 tambahan), namun tidak ada bukti cukup bahwa seluruhnya duplikat pesan.
- Timestamp pengukuran independen tidak tersedia; seluruh timestamp efektif bersumber dari penerimaan backend.

**Tindak lanjut sebelum laporan data final:**
1. Periksa alur koreksi timestamp pada firmware dan backend; dokumentasikan apakah ada buffering dan kemungkinan keterlambatan.
2. Tinjau 31 lompatan sequence serta log perangkat/MQTT untuk memahami potensi kehilangan pesan; jangan menyamakan jumlah lompatan dengan jumlah pesan hilang.
3. Cocokkan gap besar dengan log operasional dan catatan kondisi GD 525.
4. Jalankan audit ulang setelah ESP32 kedua terpasang, **per perangkat**, sebelum mempertimbangkan penggabungan data.
5. Bekukan snapshot final beserta tanggal, ukuran, checksum, dan hasil resampling/window; lakukan verifikasi kebocoran data pada tahap DE-05.

**Status DE-02:** Tahap pemeriksaan A–D telah dilakukan dan didokumentasikan. Laporan ini mencatat keterbatasan yang belum dapat diselesaikan hanya melalui isi snapshot. Tidak ada perubahan pada database sumber.
