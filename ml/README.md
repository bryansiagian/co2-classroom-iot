# ML — Prediksi CO₂ t+15 Menit (TA)

Dokumentasi ini membedakan **pipeline GD 525 terbaru yang sudah dijalankan** dari **pipeline lama `ml/src/`**. Keduanya belum memiliki kebijakan missing values yang sama. Jangan menyamakan implementasi yang sudah diuji dengan metode yang masih perlu diterapkan.

## 1. Kondisi dan keputusan metodologi

**Dokumen TA mencantumkan interpolasi untuk penanganan gap.** Karena itu, interpolasi tetap menjadi bagian dari metode penelitian yang perlu diimplementasikan dan diuji secara terkendali; **jangan menuliskan bahwa metode TA telah berubah menjadi tanpa interpolasi**.

| Bagian | Kondisi saat ini |
|---|---|
| `ml/src/clean.py` (pipeline lama `demo/real`) | Mengisi gap pendek menggunakan interpolasi linear untuk fitur numerik dan forward-fill untuk PIR, dengan kolom `filled_*`; default `MAX_GAP_MIN=3`. Pipeline ini **bukan** pipeline eksperimen GD 525 terbaru. |
| `ml/preprocessing/resample_sensor_data.py` (GD 525 terbaru) | Tidak menginterpolasi; membuat grid menit dengan status `usable`, `incomplete`, `missing`, `boundary_partial`. |
| `ml/preprocessing/build_windows.py` dan `ml/training/train_gru.py` | Tidak membuat window yang melintasi menit non-usable atau gap. |
| Metode interpolasi untuk dataset GD 525 terbaru | **Belum diimplementasikan/diuji di pipeline terbaru.** Harus diselaraskan dengan ketentuan spesifik dalam dokumen TA sebelum dipakai untuk hasil final. |

**Rencana integrasi metode TA:** Jika ketentuan dokumen TA memang menggunakan gap **maksimal 3 menit**, terapkan sebagai aturan terukur dan bertanda `filled_*`, bukan sebagai pengisian otomatis seluruh gap. Jangan menyatakan bahwa semua gap ≤3 menit sudah terisi pada dataset GD 525 yang dihasilkan oleh pipeline terbaru saat ini.

Sebelum implementasi, cocokkan dengan dokumen TA: definisi gap (menit kosong vs menit tidak lengkap), fitur yang boleh diisi, metode per fitur, batas panjang gap, dan aturan untuk data real-time.

### Pengamanan terhadap data leakage

- Untuk eksperimen **offline**, lakukan pembagian kronologis sebelum fitting scaler atau sebelum prosedur yang dapat menggunakan data dari kedua sisi batas split. Interpolasi dua sisi harus dilakukan **di dalam masing-masing split**, tidak melintasi train/validation/test, dan dilaporkan terpisah sebagai data terisi.
- Untuk inferensi **real-time**, interpolasi linear dua sisi **tidak dapat digunakan** jika titik setelah gap belum tersedia. Gunakan hanya metode kausal (data masa lalu) atau tandai data belum tersedia. Jangan menggunakan data masa depan untuk membentuk fitur pada saat prediksi dikeluarkan.
- Tidak boleh mengisi gap panjang, mengisi target evaluasi yang seharusnya ground truth, atau menutupi kegagalan sensor secara diam-diam.
- Bandingkan eksperimen **tanpa interpolasi** versus **interpolasi pendek yang sesuai TA** menggunakan validation, dan dokumentasikan proporsi baris terisi, performa, serta batasannya.

## 2. Struktur utama

```text
co2-classroom-iot/
├── backend/backend/data/
│   └── co2class_snapshot.db           # snapshot lokal, tidak masuk Git
├── ml/
│   ├── preprocessing/
│   │   ├── resample_sensor_data.py    # GD 525: SQLite -> CSV satu menit, saat ini tanpa interpolasi
│   │   └── build_windows.py           # window kontinu; tanpa gap
│   ├── training/
│   │   └── train_gru.py               # GRU, Persistence, split kronologis, scaler train-only
│   ├── data/processed/development/
│   │   └── esp32_gd525/
│   │       ├── multivariate/
│   │       └── co2_only/
│   ├── src/                            # pipeline lama demo/real, termasuk interpolasi pendek
│   ├── column_map.json                # mapping pipeline lama
│   └── README.md
└── docs/
    ├── data_quality_audit.md
    └── data_preprocessing.md
```

**Jangan unggah database, CSV sensor, kredensial, scaler, atau checkpoint ke repository publik.**

## 3. Data GD 525 dan dua profil

Pembacaan ESP32 tersimpan di tabel SQLite `sensor_reading` dan diterima umumnya setiap 10 detik. Pipeline terbaru menggunakan `received_at` (UTC) karena timestamp pengukuran independen belum terverifikasi.

Parameter resampling terbaru yang sudah berjalan:
- Grid setiap **1 menit**.
- Default **6 pembacaan diharapkan** dan **minimal 5 pembacaan valid** untuk status `usable`.
- CO₂, suhu, dan kelembapan memakai rata-rata pembacaan valid; PIR memakai nilai maksimum.
- Status menit: `missing` jika tidak ada data; `incomplete` jika kurang dari 5 record valid; `boundary_partial` untuk menit pertama/terakhir; selain itu `usable`.
- `multivariate`: CO₂, suhu, kelembapan, PIR; record dengan fault atau flag `suspect` ditolak.
- `co2_only`: CO₂ saja; fault yang hanya terkait DHT22 dapat diterima jika pembacaan CO₂ valid. Flag `suspect` ditolak.
- Rentang validasi pada kode: CO₂ 350–5.000 ppm; suhu −10–60 °C; kelembapan 0–100%; PIR 0/1.

Snapshot audit pada 23 November 2026 berisi **118.829 record**; 1.002 memiliki fault DHT22, satu memiliki flag `suspect`. Audit detail: [docs/data_quality_audit.md](../docs/data_quality_audit.md).

## 4. Menjalankan pipeline GD 525 terbaru (Windows PowerShell)

Perintah di bawah dijalankan dari **root repository**, bukan dari folder `ml/`. Aktifkan environment Python yang sudah dibuat:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Resampling SQLite menjadi CSV per menit

```powershell
python ml/preprocessing/resample_sensor_data.py `
  --db backend/backend/data/co2class_snapshot.db `
  --room gd525 --device-id esp32_gd525 `
  --profile both
```

File dibuat pada:
- `ml/data/processed/development/esp32_gd525/multivariate/all_minutes.csv`
- `ml/data/processed/development/esp32_gd525/multivariate/usable_minutes.csv`
- `ml/data/processed/development/esp32_gd525/multivariate/resample_report.json`
- `ml/data/processed/development/esp32_gd525/co2_only/` dengan tiga file sejenis.

**Peringatan:** Perintah tersebut menghasilkan **versi tanpa interpolasi**.

### Membuat window kontinu untuk pemeriksaan

```powershell
python ml/preprocessing/build_windows.py `
  --input ml/data/processed/development/esp32_gd525/multivariate/all_minutes.csv `
  --profile multivariate --lookback 60 --horizon 15 --stride 1 `
  --out-dir ml/data/processed/development/esp32_gd525/multivariate/windows
```

Input 60 observasi per menit berakhir pada `t` dan target adalah CO₂ pada `t+15`. Seluruh menit antara awal input hingga target harus `usable` dan kontinu dalam implementasi saat ini.

### Memeriksa split dan scaler tanpa training

```powershell
python ml/training/train_gru.py `
  --input ml/data/processed/development/esp32_gd525/multivariate/all_minutes.csv `
  --profile multivariate --lookback 60 --horizon 15 `
  --output ml/data/processed/development/esp32_gd525/multivariate/preparation_check `
  --prepare-only
```

Training GRU terbaru membagi berdasarkan waktu **70%/15%/15% dari menit usable** sebelum membuat window, lalu fit scaler **hanya pada train**. Persistence digunakan sebagai baseline. Script training ini memprediksi **satu titik t+15**, bukan seluruh langkah t+1 sampai t+15.

Untuk profil `co2_only`, gunakan `--profile co2_only`, CSV dari folder `co2_only`, serta `--reference-input` menunjuk CSV `multivariate/all_minutes.csv` agar menggunakan batas waktu dan target test yang diselaraskan. Target validation antarprofil **belum diselaraskan** sepenuhnya pada implementasi sekarang.

## 5. Pipeline lama: `ml/src/`

Pipeline lama `demo|real` masih tersedia dan tidak dihapus:

```text
ml/src/
  config.py          # DATA_MODE, MAX_GAP_MIN, window, horizon, batas
  guard.py           # penjagaan pemisahan mode
  load_data.py       # input CSV/XLSX dan column_map.json
  audit.py           # audit lama
  clean.py           # resampling + interpolasi pendek + filled_*
  windows.py         # window dan scaler
  models.py          # Persistence, LSTM, GRU
  train.py           # training dan perbandingan
  evaluate.py        # evaluasi lama
  predict.py         # inferensi model lama
```

Untuk menjalankannya, gunakan environment yang memiliki dependensi pada `ml/requirements.txt`, kemudian dari folder `ml/`:

```powershell
$env:DATA_MODE="demo"
python -m src.load_data
python -m src.audit
python -m src.clean
python -m src.train --windows 15 30 60 --epochs 60
python -m src.evaluate
```

Mode `real` pada pipeline lama **bukan** jaminan hasil otomatis setara dengan pipeline GD 525 terbaru. Secara khusus `ml/src/clean.py` masih mengisi gap pendek (default tiga menit) dan menghapus duplikasi berdasarkan timestamp; kebijakan ini tidak boleh langsung diterapkan tanpa audit pada data GD 525, karena pembacaan berbeda dapat diterima pada detik yang sama.

Jangan mencampur keluaran `ml/src/` (`ml/data/processed/<mode>/clean.csv`, `ml/models/<mode>/`, `ml/reports/<mode>/`) dengan keluaran pipeline GD 525 terbaru. `DATA_MODE` dan `column_map.json` **tidak mengatur** skrip `ml/preprocessing/resample_sensor_data.py`.

## 6. Penelitian dan evaluasi

- Model utama: GRU, baseline Persistence; LSTM perlu dibandingkan pada pipeline/metode evaluasi yang setara.
- Target: konsentrasi CO₂ **15 menit ke depan**.
- Evaluasi regresi: MAE, RMSE, R²; evaluasi rekomendasi ventilasi: precision, recall, F1, dan lead time.
- Pemilihan model/parameter berdasarkan **validation**, bukan berdasarkan test.
- Jika kebijakan interpolasi diselaraskan dengan TA, catat jumlah titik yang diisi, strategi penentuan target valid, dan dampaknya terhadap evaluasi.
- Dataset test lama telah berulang kali dianalisis; sediakan data baru yang belum digunakan untuk pengembangan guna mengevaluasi metode final secara lebih independen.
- Target test snapshot sebelumnya belum mengandung nilai ≥800 ppm; tidak cukup untuk menyimpulkan efektivitas peringatan 1.000 ppm.

## 7. Dokumentasi lanjutan

- [Audit kualitas data DE-02](../docs/data_quality_audit.md)
- [Dokumentasi preprocessing DE-03 (implementasi tanpa interpolasi)](../docs/data_preprocessing.md)

**Pekerjaan lanjutan:** Sinkronkan implementasi interpolasi pendek yang benar-benar tercantum di dokumen TA dengan pipeline terbaru; evaluasi secara terpisah, hindari data leakage, dan perbarui DE-03 setelah metode final diterapkan. Sampai saat itu, dokumentasi DE-03 menjelaskan **implementasi yang sudah berjalan**, bukan seluruh ketentuan metodologi TA.
