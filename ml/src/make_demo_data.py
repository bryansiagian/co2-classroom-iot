"""Generator data SINTETIS khusus untuk menguji alur pipeline (bukan data riil).

Dipakai hanya jika Anda belum punya dataset. Jika sudah punya dataset sendiri,
taruh di data/demo/ dan isi column_map.json, lalu lewati skrip ini.

    python -m src.make_demo_data --days 28

Sengaja menyertakan celah pendek/panjang, duplikat, dan outlier agar langkah audit
dan pembersihan teruji.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from . import config


def generate(days: int = 28, seed: int = config.SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-09-01 00:00", periods=days * 1440, freq="1min")
    n = len(idx)

    co2 = np.empty(n)
    occ = np.zeros(n)
    pir = np.zeros(n, dtype=int)
    ach = np.empty(n)  # laju pertukaran udara per menit

    c_out = 420.0
    gen = 0.6          # ppm/menit per orang (volume ruang efektif)
    c = c_out
    window_open_until = -1
    people = 0

    for i, t in enumerate(idx):
        mod = t.hour * 60 + t.minute
        weekday = t.weekday() < 5
        in_class = weekday and (
            450 <= mod < 600 or 615 <= mod < 720 or 780 <= mod < 930
        )
        if in_class:
            if mod in (450, 615, 780):  # awal sesi: jumlah orang baru
                people = int(rng.integers(30, 56))
            occ[i] = people
        else:
            occ[i] = 0 if not weekday else (3 if 480 <= mod < 1020 and rng.random() < 0.1 else 0)

        base_ach = 0.010
        if i < window_open_until:
            a = 0.055
        else:
            a = base_ach
            # jendela dibuka ketika CO2 tinggi, dengan peluang kecil per menit
            if occ[i] > 0 and c > 1300 and rng.random() < 0.06:
                window_open_until = i + int(rng.integers(3, 9))
        ach[i] = a

        c = c + gen * occ[i] - a * (c - c_out) + rng.normal(0, 4)
        c = max(c, 380.0)
        co2[i] = c
        pir[i] = 1 if (occ[i] > 0 and rng.random() > 0.03) else 0

    day_frac = (idx.hour * 60 + idx.minute) / 1440.0
    temp_out = 22 + 4 * np.sin((day_frac - 0.3) * 2 * np.pi) + rng.normal(0, 0.15, n)
    hum_out = 75 - 12 * np.sin((day_frac - 0.3) * 2 * np.pi) + rng.normal(0, 0.8, n)
    temp_in = temp_out + 1.5 + occ * 0.03 + rng.normal(0, 0.1, n)
    hum_in = hum_out - 8 + occ * 0.05 + rng.normal(0, 0.6, n)

    df = pd.DataFrame(
        {
            "timestamp": idx,
            "co2_ppm": co2 + rng.normal(0, 8, n),
            "temp_in_c": temp_in,
            "hum_in_pct": np.clip(hum_in, 0, 100),
            "temp_out_c": temp_out,
            "hum_out_pct": np.clip(hum_out, 0, 100),
            "pir": pir,
        }
    ).round(2)

    # --- kerusakan buatan agar audit/cleaning teruji ---
    drop = np.zeros(n, dtype=bool)
    for _ in range(40):  # celah pendek 1-3 menit
        s = int(rng.integers(0, n - 5))
        drop[s : s + int(rng.integers(1, 4))] = True
    for _ in range(6):  # celah panjang 10-90 menit
        s = int(rng.integers(0, n - 100))
        drop[s : s + int(rng.integers(10, 90))] = True
    df = df.loc[~drop].copy()

    bad = rng.choice(df.index.to_numpy(), size=8, replace=False)
    df.loc[bad[:4], "co2_ppm"] = -1.0            # nilai sensor error
    df.loc[bad[4:], "hum_in_pct"] = 150.0        # di luar rentang
    dups = df.sample(5, random_state=seed)
    df = pd.concat([df, dups]).sort_values("timestamp").reset_index(drop=True)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description="Buat data demo sintetis")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or str(config.ML_ROOT / "data" / "demo" / "synthetic_demo.csv")
    df = generate(a.days, a.seed)
    df.to_csv(out, index=False)
    print(f"{len(df)} baris -> {out}")
    print("PERINGATAN: ini data SINTETIS. Hasilnya tidak boleh dipakai sebagai hasil TA.")


if __name__ == "__main__":
    main()
