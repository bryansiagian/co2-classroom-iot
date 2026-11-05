# GD525 — Chronological Split, Persistence Baseline, GRU

Modul ini melanjutkan `ml/preprocessing/resample_sensor_data.py`. Input utamanya **`all_minutes.csv`**, bukan `usable_minutes.csv`: menit kosong/tidak lengkap wajib dipertahankan supaya tidak menciptakan deret waktu palsu.

## Prinsip

- Membaca `minute_utc`, `co2_ppm`, `temp_in_c`, `hum_in_pct`, `pir`, `status`.
- Split kronologis **70% train, 15% validation, 15% test** berdasarkan timestamp menit *usable*. Batas split ditentukan **sebelum sliding-window dibuat**.
- Window dibuat hanya jika seluruh menit dari awal input sampai waktu target `t+15` tersedia, berstatus `usable`, dan berurutan tepat satu menit. Window tidak boleh melintasi batas split.
- `StandardScaler` di-fit **hanya dari menit usable pada split train**. Scaler yang sama digunakan untuk validation/test. Target CO₂ dinormalisasi dengan mean/std CO₂ train.
- Persistence baseline: `prediksi CO₂(t+15) = CO₂(t)`.
- Model eksperimental: GRU PyTorch 1 layer, input 4 fitur, keluaran satu nilai CO₂ pada t+15. Model terbaik dipilih berdasarkan loss validasi (*early stopping*); **test hanya dievaluasi setelah training**.
- Nilai MAE/RMSE dalam ppm, R² tanpa satuan. `R2: null` apabila seluruh target identik.
- Minimal `--min-windows` (default 20) **pada tiap split** untuk melanjutkan training. Jika tidak cukup, proses tetap membuat ringkasan baseline dan mengeluarkan `insufficient_windows`, **tidak memaksakan training**.

## Cara pakai dari root repository

```bash
python3 ml/preprocessing/resample_sensor_data.py
python3 -m unittest discover -s ml/training/tests -v
python3 ml/training/train_gru.py
```

Dengan dataset development yang pendek (~89 menit usable), hasil yang **wajar** adalah status `insufficient_windows`. Itu bukan bug. Jangan gunakan data development sebagai evaluasi resmi GD525.

Untuk eksperimen yang punya cukup data, sediakan PyTorch di virtual environment ML terpisah. Contoh di lingkungan yang mengizinkan instalasi Python:

```bash
python3 -m venv ml/.venv
source ml/.venv/bin/activate
python -m pip install --upgrade pip
# Ikuti panduan install resmi PyTorch yang sesuai OS/CUDA/CPU.
python ml/training/train_gru.py --lookback 60 --horizon 15 --epochs 100 --device cpu
```

Untuk uji singkat lookback 15 menit dengan output terpisah:

```bash
python3 ml/training/train_gru.py --lookback 15 --horizon 15 \
  --output ml/data/processed/development/gru_training_15m
```

Output default (lokal, bukan untuk commit):

```text
ml/data/processed/development/gru_training/
├── scaler.json
├── training_report.json
└── gru_checkpoint.pt  # hanya jika training dilanjutkan
```

**Penting:** Jangan memakai `--device cuda` sampai PyTorch, driver, dan akses GPU pada lingkungan H200 benar-benar terverifikasi. Data development bukan data kelas GD525. Untuk pelaporan akhir, kumpulkan data resmi >=4 minggu, dokumentasikan sesi dan kondisi lapangan, ulangi split kronologis, dan bandingkan baseline vs GRU di test yang tidak dipakai saat tuning.

Catatan: pembagian berdasarkan menit *usable* adalah default awal; untuk evaluasi formal multi-sesi, tentukan batas tanggal/sesi dari protokol penelitian terlebih dahulu dan bekukan test set. Tambahkan pembandingan konfigurasi 15/30/60 menit hanya pada train/validation, jangan pilih model berdasarkan test.
