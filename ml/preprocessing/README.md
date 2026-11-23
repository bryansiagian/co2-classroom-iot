# GD525 SQLite → 1-minute preprocessing (development)

Script `resample_sensor_data.py` membaca `backend/backend/data/co2class.db` **read-only**, memfilter data yang tidak valid, kemudian membuat grid menit UTC.

## Penggunaan dari root repository

```bash
python3 ml/preprocessing/resample_sensor_data.py --device-id esp32_gd525
```

Secara default input: `backend/backend/data/co2class.db`. Output: `ml/data/processed/development/<device-id>/` (tidak ditulis ke database asli).

```bash
python3 ml/preprocessing/resample_sensor_data.py --db /lokasi/co2class.db --room gd525 --device-id esp32_gd525 --expected 6 --min-samples 5
python3 ml/preprocessing/resample_sensor_data.py --device-id esp32_gd525_02
python3 -m unittest discover -s ml/preprocessing/tests -v
```

Filter `--device-id` diwajibkan melalui CLI agar data dari dua ESP32 tidak bercampur. Fungsi Python `resample()` masih menerima pemanggilan tanpa filter untuk kompatibilitas dengan kode lama, tetapi jalur ini tidak boleh dipakai untuk pengolahan multi-perangkat. Gunakan `--out` untuk menentukan folder keluaran alternatif. Database tetap dibuka read-only.

## File keluaran

- `all_minutes.csv`: grid menit utuh, termasuk `missing`, `incomplete`, dan `boundary_partial`.
- `usable_minutes.csv`: hanya menit internal dengan sedikitnya 5 pembacaan valid (default).
- `resample_report.json`: ringkasan kualitas dan jumlah sampel terbuang.

Per menit, CO₂/suhu/RH = rerata; PIR = maksimum; `n_received`, `n_valid`, `n_rejected`, `coverage_pct` dan `status` disimpan untuk audit.

**Status:**
- `usable`: menit internal dengan >= `--min-samples` pembacaan valid;
- `incomplete`: menit internal yang sampel validnya kurang;
- `missing`: menit tanpa data;
- `boundary_partial`: menit pertama/terakhir rekaman yang tidak dapat dijamin durasinya penuh.

**Batasan penting:** Ini ekspor data *development*, bukan data resmi ruang GD525. Timestamp memakai `received_at` H200 karena firmware V4.1 belum mengirim waktu ukur terverifikasi. `ts_corrected` sendiri tidak membatalkan data. Tidak ada interpolasi, sehingga baris `usable_minutes.csv` **jangan disambung langsung** menjadi sliding window GRU melewati gap. Pertahankan grid `all_minutes.csv` untuk membangun segmen waktu kontinu dan split kronologis.

Jangan commit file keluaran CSV/JSON dari rekaman asli. Tambahkan ke `.gitignore`:

```gitignore
/ml/data/processed/development/
```

Script ini melengkapi `ml/src/clean.py` yang sudah ada; belum otomatis tersambung ke `ml/src/train.py`.


## DE-04: dua profil kualitas dataset
```powershell
python ml/preprocessing/resample_sensor_data.py `
    --db backend/backend/data/co2class_snapshot.db `
    --device-id esp32_gd525 `
    --profile both
```

Dengan `--profile both` dua set output ditulis di bawah `ml/data/processed/development/esp32_gd525/`:
- `multivariate/{all_minutes.csv,usable_minutes.csv,resample_report.json}` memakai kebijakan lama (CO2, DHT22, PIR wajib valid).
- `co2_only/{all_minutes.csv,usable_minutes.csv,resample_report.json}` menggunakan CO2 valid, dan mengizinkan *hanya* fault `temperature`/`humidity`. Fault lain, quality flag suspect, CO2 kosong/di luar rentang tetap ditolak. Fitur non-CO2 sengaja ditulis kosong; jangan dijadikan input model multivariat.
- Tanpa `--profile` perilaku lama tetap berlaku dan output langsung berada di direktori `<device-id>`. Mode `both` tidak menimpa file output lama pada direktori tersebut.

`n_valid` dan `coverage_pct` dihitung menurut kriteria profil yang dipilih, sehingga satu menit dapat usable pada CO2-only tetapi incomplete pada multivariate. Tidak ada interpolasi. Besarnya penambahan menit/window harus dihitung ulang dari hasil ekspor, tidak disimpulkan dari jumlah record fault. Kedua profil tetap memerlukan pemisahan kronologis sebelum evaluasi GRU; perbandingan model harus menggunakan timestamp test yang sama.


## Membentuk kandidat window per profil (belum split)
```powershell
python ml/preprocessing/build_windows.py `
    --input ml/data/processed/development/esp32_gd525/co2_only/all_minutes.csv `
    --out-dir ml/data/processed/development/esp32_gd525/co2_only/windows `
    --profile co2_only --lookback 60 --horizon 15

python ml/preprocessing/build_windows.py `
    --input ml/data/processed/development/esp32_gd525/multivariate/all_minutes.csv `
    --out-dir ml/data/processed/development/esp32_gd525/multivariate/windows `
    --profile multivariate --lookback 60 --horizon 15
```

Kedua perintah ini **hanya untuk audit kandidat window**: hasil `windows.jsonl` belum dibagi train/validation/test. Jangan menggunakan window tumpang tindih hasil ekspor ini untuk random split. Untuk eksperimen model, lakukan split waktu yang mencegah window input dan target melintasi batas split. Perbandingan univariat vs multivariat menggunakan target timestamp test yang sama. Jalankan unit test setelah pull:
`python -m unittest discover -s ml/preprocessing/tests -p "test_*.py" -v`.


## ML-01: split bersama dan persiapan GRU tanpa training

Jalankan dari root repository. Dataset multivariate digunakan sebagai acuan batas split bersama dan himpunan target pengujian yang identik untuk kedua model.

```powershell
$base = "ml/data/processed/development/esp32_gd525"
$reference = "$base/multivariate/all_minutes.csv"

python ml/training/train_gru.py `
    --input $reference `
    --profile multivariate `
    --reference-input $reference `
    --output "$base/multivariate/gru_training" `
    --prepare-only

python ml/training/train_gru.py `
    --input "$base/co2_only/all_minutes.csv" `
    --profile co2_only `
    --reference-input $reference `
    --output "$base/co2_only/gru_training" `
    --prepare-only
```

`--prepare-only` menulis `training_report.json` dan `scaler.json` tanpa PyTorch dan tanpa melatih model. `--reference-input` menetapkan batas waktu berdasarkan menit usable multivariate dan membatasi window test kepada timestamp target yang tersedia pada profil referensi. Saat nanti training, kode GRU memakai `input_size=1` untuk `co2_only` dan `input_size=4` untuk `multivariate`. Setiap profil tetap fitting scaler hanya pada train. Tidak ada pengisian gap. Perbandingan final harus memverifikasi timestamp dan nilai target kedua hasil prediksi, bukan hanya jumlah window.


### Acuan label CO2 pada evaluasi
Meskipun target timestamp sama, nilai agregasi CO2 bisa sedikit berbeda antarprofil ketika DHT22 gagal. Pada tahap test, jalur `--reference-input` sekarang juga menyelaraskan **nilai target aktual CO2** ke dataset multivariat yang sama untuk kedua eksperimen. Selisih sebelum penyelarasan dicatat sebagai `test_target_alignment.changed_target_values` dan `maximum_absolute_target_difference_ppm`. Input sequence tetap berasal dari profil masing-masing. Saat model benar-benar dilatih, `test_predictions.csv` berisi timestamp target, nilai aktual kanonis, prediksi GRU, dan prediksi Persistence untuk audit per timestamp. Semua hasil lokal berada di direktori preprocessing yang diabaikan Git.
