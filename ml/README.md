# ml/ — Prediksi CO₂ t+15 menit (LSTM/GRU) untuk TA

Folder ini berisi seluruh alur data → model → evaluasi. Satu kode untuk dua mode:
`demo` (dataset yang sudah ada) dan `real` (data dari alat). Yang berganti hanya data dan model.

## Struktur

```
ml/
├── column_map.json        # pemetaan kolom dataset Anda -> kontrak data (EDIT INI)
├── requirements.txt
├── data/
│   ├── demo/              # taruh dataset demo (CSV/XLSX) di sini
│   ├── real/              # data dari alat (nanti)
│   └── processed/<mode>/  # hasil pembersihan (clean.csv)
├── models/<mode>/         # model + scaler + meta (gru/, lstm/, persistence/)
├── reports/<mode>/        # audit, tabel metrik, grafik
├── notebooks/             # eksplorasi bebas
└── src/
    ├── config.py          # parameter (horizon 15, split 70/15/15, ambang 800/1000/1500)
    ├── guard.py           # menolak data/model demo di mode riil
    ├── load_data.py       # muat CSV/XLSX + pemetaan kolom
    ├── audit.py           # audit kualitas data
    ├── clean.py           # rapikan ke 1 menit + tandai data hasil isian
    ├── windows.py         # jendela N menit, split kronologis, scaler dari train saja
    ├── models.py          # Persistence, LSTM, GRU (PyTorch)
    ├── metrics.py         # MAE, RMSE, R2 (+ per langkah t+1..t+15)
    ├── train.py           # latih + bandingkan
    ├── evaluate.py        # grafik + evaluasi proaktif vs reaktif
    ├── predict.py         # inferensi untuk GRUPredictor di backend
    └── make_demo_data.py  # data SINTETIS khusus uji alur (opsional)
```

## Pemasangan

```bash
cd ml
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
```

Gunakan `.venv` terpisah dari backend. Backend hanya perlu `torch` untuk memuat model.

## Alur (jalankan dari folder ml/)

Mode dipilih lewat variabel `DATA_MODE` (default `demo`), atau argumen `--mode`.

```bash
# 1. Taruh dataset di data/demo/, lalu edit column_map.json
python -m src.load_data          # cek pemetaan kolom (tampilkan 10 baris)

# (opsional) belum punya dataset? buat data sintetis untuk uji alur
python -m src.make_demo_data --days 28

# 2. Audit kualitas  -> reports/demo/audit.md
python -m src.audit

# 3. Bersihkan       -> data/processed/demo/clean.csv, reports/demo/clean.md
python -m src.clean

# 4. Latih + bandingkan Persistence / LSTM / GRU (N = 15, 30, 60)
python -m src.train --windows 15 30 60 --epochs 60

# 5. Grafik + evaluasi proaktif vs reaktif
python -m src.evaluate
```

Windows PowerShell: set mode dengan `$env:DATA_MODE="real"`. CMD: `set DATA_MODE=real`.

## Pemetaan kolom (column_map.json)

Kunci di kiri tetap, isi nilai kanan dengan nama kolom di dataset Anda. Kolom yang
tidak ada diisi `null` (otomatis tidak dipakai sebagai fitur). Wajib: `timestamp` dan `co2_ppm`.
Jika format waktu khusus, isi `_timestamp_format` (mis. `"%d/%m/%Y %H:%M:%S"`).

## Aturan penting

1. **Hasil dari data demo tidak boleh masuk laporan/slide TA.** Semua laporan mode demo diberi tanda "DATA DEMO".
2. Di mode `real`, semua skrip menolak berjalan jika berkas/model berasal dari folder `demo`
   (`guard.py`), dan model hanya dimuat jika `meta.json` mencatat `data_mode` yang sama.
3. Scaler dihitung hanya dari bagian train. Split kronologis; jendela tidak melintasi batas split.
4. Jendela yang melewati celah (NaN) dibuang. Celah <= 3 menit diinterpolasi dan ditandai di kolom `filled_*`.
5. Pemilihan N terbaik memakai RMSE **validasi**, bukan data uji.

## Memakai model di backend

```python
from src.predict import GRUModel
model = GRUModel.load("models/demo/gru", mode="demo")
pred = model.predict(df_recent)   # dict: {"t+1": ..., ..., "t+15": ...}
```

`df_recent` harus berisi minimal `window` baris terakhir pada grid 1 menit dengan kolom
sesuai `meta.json["features"]`.

## Beralih ke mode riil

1. Simpan data alat di `data/real/` (CSV), cek `column_map.json`.
2. `set DATA_MODE=real` lalu ulangi audit → clean → train → evaluate.
3. Model riil tersimpan di `models/real/` (terpisah dari demo).
