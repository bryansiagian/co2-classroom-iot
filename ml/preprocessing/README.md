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
