# Dokumentasi Pipeline Preprocessing Data CO₂ GD 525

**Kode pekerjaan:** DE-03  
**Tanggal dokumentasi:** 23 November 2026  
**Perangkat yang sudah diproses:** `esp32_gd525`  
**Ruang:** `gd525`  
**Status:** Dokumentasi implementasi preprocessing pada branch `bryan/data-ml-engineering`; dataset yang dibahas adalah snapshot pengembangan, bukan dataset final penelitian.

Dokumen ini menjelaskan **alur yang benar-benar diimplementasikan** dari SQLite sampai data siap untuk eksperimen GRU. Temuan kualitas data dijelaskan lebih terperinci dalam [Laporan DE-02](data_quality_audit.md).

## 1. Tujuan dan ruang lingkup

Data sensor dari ESP32 diterima oleh backend dan disimpan pada tabel `sensor_reading` dalam SQLite. Interval pengiriman umumnya sekitar 10 detik, sedangkan model memerlukan rangkaian data satu menit. Preprocessing bertujuan untuk:

1. Memilih data sesuai `room_id` dan `device_id` tanpa mencampurkan dua perangkat.
2. Memvalidasi kualitas pembacaan, termasuk fault DHT22 dan flag `suspect`.
3. Mengubah pembacaan menjadi grid UTC setiap satu menit.
4. Membedakan menit layak pakai, tidak lengkap, hilang, dan menit batas.
5. Membuat window historis kontinu untuk target CO₂ 15 menit ke depan.
6. Menyiapkan pembagian train/validation/test kronologis dan normalisasi tanpa menggunakan informasi masa depan.

Preprocessing **tidak mengubah SQLite sumber**, **tidak melakukan interpolasi**, dan **tidak menghapus record mentah**.

## 2. Sumber dan batasan waktu

| Atribut | Nilai |
|---|---|
| Sumber development | `backend/backend/data/co2class_snapshot.db` |
| Tabel | `sensor_reading` |
| Filter ruang | `gd525` |
| Filter perangkat | `esp32_gd525` |
| Jumlah record pada snapshot audit | 118.829 |
| Pembacaan pertama | `2026-11-04T14:03:01Z` |
| Pembacaan terakhir | `2026-11-23T02:16:51Z` |
| Kolom timestamp yang digunakan | `received_at` (UTC) |

Alasan memilih `received_at`: snapshot belum memiliki timestamp pengukuran perangkat yang terverifikasi. Seluruh `measured_at_utc` kosong dan seluruh `ts_utc` sama dengan `received_at`; seluruh record ditandai `ts_corrected`. Oleh karena itu, data dihimpun menurut **waktu penerimaan backend**, dan keterlambatan pengiriman dapat memengaruhi atribusi menit. Jangan menyebut `received_at` sebagai waktu pengukuran aktual ESP32.

Database aktif H200 terus bertambah; seluruh angka dalam dokumen ini merujuk pada **snapshot lokal** di atas.

## 3. Alur dan file implementasi

```text
SQLite snapshot: sensor_reading (pembacaan ~10 detik)
      |
      | ml/preprocessing/resample_sensor_data.py
      | filter room_id/device_id, parsing UTC, validasi kualitas,
      | agregasi satu menit, status kelengkapan
      v
ml/data/processed/development/esp32_gd525/
  ├── multivariate/
  │   ├── all_minutes.csv
  │   ├── usable_minutes.csv
  │   └── resample_report.json
  └── co2_only/
      ├── all_minutes.csv
      ├── usable_minutes.csv
      └── resample_report.json
      |
      | ml/preprocessing/build_windows.py
      | pecah segmen pada menit unusable atau timestamp tidak kontinu
      v
windows.jsonl + windows_index.csv + windows_report.json
      |
      | ml/training/train_gru.py
      | split kronologis dulu, buat ulang window per split,
      | fit scaler hanya dari train, latih/evaluasi
      v
GRU / Persistence (eksperimen development)
```

**Penting:** File window dari `build_windows.py` digunakan untuk inspeksi/ekspor window. **Training GRU tidak membaca `windows.jsonl`**: `train_gru.py` membaca `all_minutes.csv`, menentukan batas split **sebelum** membuat window dan membentuk window secara terpisah di masing-masing split. Pemisahan ini diperlukan untuk mencegah window yang saling overlap menyeberangi batas train/validation/test.

## 4. Seleksi data dan pemeriksaan kualitas

Script: [`ml/preprocessing/resample_sensor_data.py`](../ml/preprocessing/resample_sensor_data.py).

Script membaca kolom `received_at`, `co2_ppm`, `temp_in_c`, `hum_in_pct`, `pir`, `quality_flags`, dan `faults` dengan `ORDER BY received_at, id`. Setiap timestamp harus dapat diparse dan memiliki zona waktu, lalu dinormalisasi ke UTC.

### 4.1 Dua profil

| Aspek | `multivariate` | `co2_only` |
|---|---|---|
| Fitur model | CO₂, suhu, kelembapan, PIR | CO₂ |
| Flag `suspect` / akhiran `_suspect` | Tolak | Tolak |
| Fault `temperature`/`humidity` | Tolak | Boleh bila hanya fault tersebut |
| Fault lain | Tolak | Tolak |
| Pemeriksaan nilai | Keempat fitur | CO₂ |
| Fitur non-CO₂ pada output `co2_only` | — | Dikosongkan |

Flag `ts_corrected` tidak otomatis ditolak karena hanya waktu penerimaan yang tersedia pada snapshot. Untuk kedua profil, nilai `quality_flags` dan `faults` harus dapat diparse menjadi daftar JSON yang sesuai dengan validasi.

### 4.2 Rentang yang diterapkan dalam kode

| Fitur | Rentang valid |
|---|---|
| `co2_ppm` | 350–5.000 ppm, inklusif |
| `temp_in_c` | −10 sampai 60 °C, inklusif |
| `hum_in_pct` | 0–100%, inklusif |
| `pir` | Integer 0 atau 1 |

Nilai nonnumerik, non-finite, dan di luar batas ditolak pada fitur yang diwajibkan profil. Batas ini merupakan **aturan validasi operasional pipeline**, bukan ambang rekomendasi ventilasi. Nilai CO₂ tinggi di dalam rentang tidak otomatis dibuang.

Pada snapshot audit ditemukan **1.002 record fault suhu+kelembapan** dan **1 record berflag `suspect`**. Keputusan resampling bergantung pada profil. Penghitungan alasan penolakan tersedia dalam `resample_report.json`.

## 5. Resampling dari ~10 detik ke satu menit

Konfigurasi default:

- `--expected 6`: perkiraan 6 pembacaan per menit pada interval 10 detik.
- `--min-samples 5`: perlu sedikitnya 5 pembacaan **valid** agar satu menit interior berstatus `usable`.
- Timestamp dikelompokkan dengan membuang komponen detik/mikrodetik dari `received_at` setelah konversi UTC.
- Grid menit dibuat **kontinu dari menit pertama hingga menit terakhir**; menit tanpa record tetap dituliskan.

### 5.1 Aturan agregasi

| Kolom keluaran | Cara menghitung |
|---|---|
| `minute_utc` | Awal menit UTC |
| `co2_ppm` | Rata-rata CO₂ dari record valid pada menit tersebut, dibulatkan 3 desimal |
| `temp_in_c` | Rata-rata suhu valid untuk profil multivariate |
| `hum_in_pct` | Rata-rata kelembapan valid untuk profil multivariate |
| `pir` | Maksimum PIR valid (1 bila ada gerakan terdeteksi pada salah satu sampel valid di menit itu) |
| `n_received` | Semua record yang diterima pada menit tersebut |
| `n_valid` | Jumlah record yang lolos aturan profil |
| `n_rejected` | `n_received - n_valid` |
| `coverage_pct` | `min(100, 100 × n_valid / expected)`, dibulatkan 1 desimal |
| `status` | Status kelengkapan menit |

Pada `co2_only`, nilai `temp_in_c`, `hum_in_pct`, dan `pir` pada CSV hasil resampling **dikosongkan**, bukan disalin dari nilai sensor.

### 5.2 Penetapan status menit

Urutan aturan yang benar sesuai kode:

1. **`missing`** jika tidak ada satu pun record pada menit itu.
2. **`boundary_partial`** jika menit tersebut adalah menit pertama/terakhir dalam rentang snapshot dan terdapat record; status ini ditetapkan sebelum mengevaluasi jumlah minimal valid.
3. **`incomplete`** jika jumlah record valid kurang dari 5 (default), untuk menit interior yang tidak kosong.
4. **`usable`** jika menit interior memiliki sedikitnya 5 record valid.

Menit dengan record masuk tetapi semuanya ditolak tetap `incomplete`, bukan `missing`. Dua menit batas tidak digunakan untuk training meskipun jumlah pembacaan cukup.

**Tidak ada interpolasi** atas menit `missing` maupun `incomplete`; kedua status tersebut memutus kontinuitas window.

## 6. Format keluaran dan fungsi masing-masing

Untuk setiap profil:

- `all_minutes.csv`: seluruh grid waktu menit, termasuk baris `usable`, `missing`, `incomplete`, dan `boundary_partial`. Ini sumber yang digunakan script window dan training.
- `usable_minutes.csv`: hanya menit berstatus `usable`; cocok untuk ringkasan nilai, tetapi **jangan langsung** dipakai membuat window tanpa memeriksa kontinuitas timestamp.
- `resample_report.json`: metadata perangkat/profil/sumber, jumlah record, jumlah penolakan per alasan, total/usable/incomplete/missing/boundary, dan peringatan penggunaan data.

`all_minutes.csv` mempertahankan posisi menit kosong untuk kepentingan audit dan pencegahan window yang melewati gap.

## 7. Sliding window dan target prediksi

Script: [`ml/preprocessing/build_windows.py`](../ml/preprocessing/build_windows.py).

Parameter default:

| Parameter | Nilai | Arti |
|---|---:|---|
| `lookback` | 60 | 60 observasi per menit sebagai fitur input |
| `horizon` | 15 | Target CO₂ tepat 15 menit setelah **observasi input terakhir** |
| `stride` | 1 | Pergeseran titik awal window per 1 menit |

Jika input berakhir pada menit `t`, target berada di menit `t+15`. Input terdiri dari menit `t-59` sampai `t`. Untuk membentuk window, seluruh menit mulai `t-59` sampai `t+15` harus tersedia, berurutan tepat satu menit, dan berstatus `usable` — termasuk menit di antara input terakhir dan target.

Secara indeks untuk suatu segmen kontinu:
- Input = `segment[start : start + lookback]`.
- Target = `segment[start + lookback + horizon - 1]`.
- Panjang minimal segmen = `lookback + horizon` = 75 menit.

Kode memutus segmen jika bertemu menit unusable atau loncatan timestamp. Nilai fitur tidak boleh `NaN`/`Inf`; PIR multivariat harus 0 atau 1.

File keluaran (di folder yang dipilih melalui `--out-dir`):
- `windows.jsonl`: array fitur `X`, target `y_co2_ppm`, waktu input dan target.
- `windows_index.csv`: ringkasan identitas window dan timestamp/target.
- `windows_report.json`: jumlah segmen, panjang maksimum segmen, jumlah window, konfigurasi, dan peringatan.

## 8. Split kronologis dan normalisasi untuk training

Script: [`ml/training/train_gru.py`](../ml/training/train_gru.py).

Langkahnya:
1. Baca `all_minutes.csv` per profil menurut urutan waktu; timestamp wajib naik ketat dan unik.
2. Tentukan **batas waktu** pada menit berstatus `usable` untuk rasio sekitar **70% train, 15% validation, 15% test**. Rasio ini dihitung dari **menit usable**, bukan dari jumlah window akhir.
3. Bagi seluruh baris menit sesuai batas waktu, **baru** bentuk window secara terpisah di train, validation, dan test.
4. Semua observasi input, menit penghubung hingga target, dan target window harus berada di split yang sama; tidak ada window menyeberangi batas split.
5. Fit `StandardScaler` hanya pada fitur menit usable **di train**; gunakan parameter yang sama untuk validation/test. Target CO₂ juga dinormalisasi dengan rata-rata dan simpangan baku CO₂ dari train.
6. Hitung Persistence baseline menggunakan **CO₂ pada input terakhir** sebagai prediksi `t+15`; jalankan training GRU dan catat metrik MAE, RMSE, R².

Pada eksperimen dua profil, opsi `--reference-input` (CSV multivariate) menentukan batas waktu bersama untuk profil CO₂-only dan menyelaraskan **timestamp dan label target test** terhadap referensi. **Validasi belum diselaraskan dengan cara yang sama**; karenanya nilai validation antarprofil tidak boleh diklaim sebagai perbandingan tepat berpasangan tanpa penyelarasan tambahan.

Hasil pengujian test yang telah dilihat beberapa kali **tidak boleh dipakai untuk memilih hyperparameter atau ambang yang optimal**. Lakukan pemilihan model pada validation dan sisihkan data baru yang belum dipakai untuk evaluasi akhir.

### Batas waktu split yang tercatat pada eksperimen snapshot

| Batas | Timestamp UTC |
|---|---|
| Train berakhir | `2026-11-18T21:51:00+00:00` |
| Validation berakhir | `2026-11-20T23:27:00+00:00` |

Batas ini berlaku untuk snapshot/konfigurasi eksperimen tersebut, **bukan** batas baku untuk seluruh pengumpulan data berikutnya.

## 9. Hasil pipeline pada snapshot development

Ringkasan di bawah diambil dari hasil eksekusi preprocessing/window yang telah dicatat pada snapshot lokal 118.829 record; bukan hasil menjalankan ulang pipeline saat penulisan dokumen.

| Metrik | Multivariate | CO₂-only |
|---|---:|---:|
| Menit usable | 19.818 | 19.836 |
| Menit incomplete | 60 | 42 |
| Menit missing | 6.774 | 6.774 |
| Segmen usable kontinu | 49 | 31 |
| Segmen terpanjang (menit) | 3.749 | 12.079 |
| Window 60→15 menit (sebelum split) | 17.370 | 18.566 |

Untuk training eksperimen dengan batas split kronologis, jumlah window masing-masing tercatat sebagai berikut:

| Split | Multivariate | CO₂-only |
|---|---:|---:|
| Train | 11.948 | 12.838 |
| Validation | 2.602 | 2.902 |
| Test | 2.672 | 2.672 |

Angka total window sebelum split **tidak harus** sama dengan penjumlahan seluruh window per split, karena window yang menyeberangi batas kronologis sengaja tidak dibuat. Sumber audit hasil: `resample_report.json`, `windows_report.json`, dan `training_report.json` pada keluaran lokal masing-masing profil.

## 10. Cara menjalankan ulang (Windows PowerShell)

Dari root repository, aktifkan virtual environment bila tersedia:

```powershell
.\.venv\Scripts\Activate.ps1
```

Gunakan snapshot lokal sebagai sumber **read-only**:

```powershell
python ml/preprocessing/resample_sensor_data.py `
  --db backend/backend/data/co2class_snapshot.db `
  --room gd525 `
  --device-id esp32_gd525 `
  --profile both
```

Keluaran ada di `ml/data/processed/development/esp32_gd525/{multivariate,co2_only}/`.

Buat window untuk pemeriksaan masing-masing profil:

```powershell
python ml/preprocessing/build_windows.py `
  --input ml/data/processed/development/esp32_gd525/multivariate/all_minutes.csv `
  --profile multivariate `
  --lookback 60 --horizon 15 --stride 1 `
  --out-dir ml/data/processed/development/esp32_gd525/multivariate/windows

python ml/preprocessing/build_windows.py `
  --input ml/data/processed/development/esp32_gd525/co2_only/all_minutes.csv `
  --profile co2_only `
  --lookback 60 --horizon 15 --stride 1 `
  --out-dir ml/data/processed/development/esp32_gd525/co2_only/windows
```

Periksa pemisahan train/val/test **tanpa menjalankan training GRU**:

```powershell
python ml/training/train_gru.py `
  --input ml/data/processed/development/esp32_gd525/multivariate/all_minutes.csv `
  --output ml/data/processed/development/esp32_gd525/multivariate/preparation_check `
  --profile multivariate --lookback 60 --horizon 15 --prepare-only

python ml/training/train_gru.py `
  --input ml/data/processed/development/esp32_gd525/co2_only/all_minutes.csv `
  --reference-input ml/data/processed/development/esp32_gd525/multivariate/all_minutes.csv `
  --output ml/data/processed/development/esp32_gd525/co2_only/preparation_check `
  --profile co2_only --lookback 60 --horizon 15 --prepare-only
```

Opsi `--prepare-only` **menulis laporan dan scaler** pada folder output, tetapi tidak melatih GRU.

> **Catatan:** Jangan menjalankan opsi output yang menimpa hasil eksperimen penting tanpa menyalin laporan/artefaknya terlebih dahulu. Semua data mentah, snapshot database, CSV hasil pemrosesan, dan file model harus tetap di luar commit repository publik.

## 11. Kualitas, reproducibility, dan pekerjaan berikutnya

- Pada snapshot awal ada fault DHT22, gap panjang, timestamp yang berulang, dan `received_at` yang belum mewakili waktu ukur independen; lihat [DE-02](data_quality_audit.md).
- PIR adalah **indikator gerakan**, bukan penghitung jumlah orang. Nilai `pir=1` setelah agregasi berarti setidaknya satu pembacaan valid pada menit itu mendeteksi gerakan.
- Rasio split kronologis didasarkan pada jumlah menit usable; perbedaan panjang segmen membuat jumlah window berbeda.
- Setelah ESP32 kedua aktif, lakukan resampling **terpisah berdasarkan `device_id`** dan audit per perangkat. Jangan langsung mencampurkan dua aliran pembacaan.
- Saat data final tersedia, bekukan snapshot beserta checksum, rerun pipeline, catat versi kode/parameter, ulang audit kualitas dan kebocoran data (DE-05), serta siapkan evaluasi terpisah pada data baru.
- Klaim model proaktif pada ambang 1.000 ppm belum dapat dibuktikan dari test snapshot saat ini karena belum terdapat target test CO₂ di atas ambang tersebut.

**Status DE-03:** Alur preprocessing, parameter, aturan validasi, keluaran, serta interaksi dengan training GRU telah didokumentasikan berdasarkan implementasi repository. Dokumentasi tidak menggantikan validasi dataset final (DE-05/DE-06).
