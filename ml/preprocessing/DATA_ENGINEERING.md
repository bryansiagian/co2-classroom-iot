# Kontribusi Data Engineering dan Preprocessing

## Alur

1. `resample_sensor_data.py` membuka SQLite dalam mode read-only dan membaca tabel `sensor_reading`.
2. Waktu yang dipakai adalah `received_at` UTC karena firmware V4.1 belum menyediakan timestamp pengukuran yang terverifikasi.
3. Pembacaan dikelompokkan ke grid satu menit. CO₂, suhu, dan RH dirata-ratakan; PIR diagregasi dengan maksimum.
4. Satu menit dinyatakan `usable` jika merupakan menit internal dan mempunyai minimal 5 dari 6 sampel valid secara default. Menit tidak lengkap, kosong, atau di batas rekaman tidak digunakan untuk membentuk window.
5. `build_windows.py` membentuk input multivariat (default 60 menit) dan satu target CO₂ tepat 15 menit setelah akhir input. Semua menit di antara input dan target harus usable dan berjarak tepat satu menit.
6. `ml/training/train_gru.py` melakukan split kronologis sebelum windowing dan fitting scaler hanya pada data train.

## Kebijakan kualitas

- Rentang operasional fitur di pipeline SQLite: CO₂ 350–5000 ppm, suhu -10–60 °C, RH 0–100%, PIR 0/1.
- Flag kualitas `suspect` dan flag dengan akhiran `_suspect` ditolak.
- Missing value tidak diinterpolasi atau di-forward-fill. Window yang melintasi menit tidak usable dibuang.
- Database sumber dibuka read-only dan tidak dimodifikasi.
- `filled_*` pada jalur `ml/src/clean.py` dipertahankan untuk kompatibilitas, tetapi selalu 0 karena tidak ada imputasi.

## Perintah verifikasi

Dari root repository:

```bash
python -m unittest discover -s ml/src/tests -v
python -m unittest discover -s ml/preprocessing/tests -v
python -m unittest discover -s ml/training/tests -v
```

## Batasan saat ini

- Data development tidak boleh diklaim sebagai hasil pengukuran resmi GD525.
- Timestamp penerimaan server bukan timestamp sensor yang terverifikasi.
- Data SQLite resmi belum disertakan dalam repository; ekspor dataset nyata harus dijalankan di lingkungan yang mempunyai akses ke database.
- File hasil ekspor CSV/JSON dan database tidak boleh di-commit.
