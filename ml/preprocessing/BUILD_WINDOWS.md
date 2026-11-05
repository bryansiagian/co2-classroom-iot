# Sliding window GRU — GD525 (development)

`build_windows.py` membentuk dataset multivariat **CO₂, suhu, RH, PIR** dari `all_minutes.csv` yang dihasilkan oleh `resample_sensor_data.py`.

## Cara menjalankan (dari root repository)

```bash
python3 ml/preprocessing/resample_sensor_data.py
python3 ml/preprocessing/build_windows.py
python3 -m unittest discover -s ml/preprocessing/tests -v
```

Secara default: `--lookback 60 --horizon 15 --stride 1`, input `ml/data/processed/development/all_minutes.csv`, output `ml/data/processed/development/windows/`.

Untuk uji cepat pada dataset yang pendek:

```bash
python3 ml/preprocessing/build_windows.py --lookback 15 --horizon 15
```

*Aturan:* Untuk input sebanyak `L` menit yang berakhir pada `t`, target `y` adalah CO₂ pada tepat `t + H` menit. Semua menit mulai input pertama **sampai target** harus `status=usable`, berurutan satu menit persis. `incomplete`, `missing`, `boundary_partial` serta loncatan timestamp akan memutus segmen. Tidak ada interpolasi.

Minimum satu window adalah `L + H` baris menit kontinu (60+15=75), bukan 60+15+1, karena target dihitung relatif terhadap **menit terakhir input**.

## Output

- `windows.jsonl`: tiap baris satu objek berisi `window_id`, timestamp, `features`, `X` (array `[L,4]`), dan `y_co2_ppm` (nilai target).
- `windows_index.csv`: ringkasan timestamp dan target setiap window, untuk audit.
- `windows_report.json`: jumlah window, jumlah segmen, dan peringatan metode.

CSV sumber dan database SQLite **tidak dimodifikasi**. Jangan commit berkas dataset ke GitHub.

## Langkah berikutnya sebelum training

1. Data saat ini hanya **development**, bukan hasil pengukuran resmi GD525.
2. Lakukan **split kronologis** train/validation/test (misalnya 70/15/15) sebelum fitting scaler. Jangan split window acak; window overlap akan bocor antar split. Perlu pertimbangkan jarak/embargo antarsplit atau membentuk window setelah split segment berdasarkan waktu target.
3. Fitting normalisasi hanya pada train, lalu terapkan parameter train ke validation/test.
4. Bandingkan persistence dan GRU menggunakan MAE, RMSE, R² pada target waktu yang identik.
5. Uji kandidat panjang input (misalnya 15, 30, 60 menit), jangan menganggap 60 menit sudah optimal.

Jika CSV development pendek, output 0 window adalah hasil valid, bukan error.
