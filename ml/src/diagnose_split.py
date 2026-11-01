"""Diagnosis: apa isi masing-masing split (train/val/test)?

    python -m src.diagnose_split
"""
from __future__ import annotations

import argparse

import pandas as pd

from . import config
from .windows import split_bounds


def main() -> None:
    ap = argparse.ArgumentParser(description="Diagnosis isi split data")
    ap.add_argument("--mode", default=None)
    a = ap.parse_args()
    mode = config.get_mode(a.mode)
    p = config.paths(mode)
    df = pd.read_csv(p["processed_dir"] / "clean.csv", parse_dates=["timestamp"])
    b = split_bounds(len(df))

    print(f"Mode={mode}  baris={len(df)}\n")
    print("=== Ringkasan per split ===")
    for name, (lo, hi) in b.items():
        s = df.iloc[lo:hi]
        co2 = s[config.TARGET]
        row = {
            "split": name,
            "mulai": s["timestamp"].iloc[0],
            "akhir": s["timestamp"].iloc[-1],
            "hari": round(len(s) / 1440, 2),
            "co2_mean": round(co2.mean(), 1),
            "co2_std": round(co2.std(), 1),
            "co2_max": round(co2.max(), 1),
            "%>=800": round(100 * (co2 >= 800).mean(), 1),
            "%>=1000": round(100 * (co2 >= 1000).mean(), 1),
            "%>=1500": round(100 * (co2 >= 1500).mean(), 1),
        }
        if "pir" in s.columns:
            row["pir_mean"] = round(s["pir"].mean(), 3)
        print(row)

    print("\n=== Per hari (split tempat hari itu berada, berdasarkan jam pertama) ===")
    df["split"] = ""
    for name, (lo, hi) in b.items():
        df.loc[df.index[lo:hi], "split"] = name
    df["tanggal"] = df["timestamp"].dt.date
    g = df.groupby("tanggal").agg(
        hari=("timestamp", lambda t: t.iloc[0].day_name()[:3]),
        split=("split", lambda x: "/".join(sorted(set(x), key=["train", "val", "test"].index))),
        co2_mean=(config.TARGET, "mean"),
        co2_max=(config.TARGET, "max"),
        pir_mean=("pir", "mean") if "pir" in df.columns else (config.TARGET, "size"),
    ).round(1)
    print(g.to_string())


if __name__ == "__main__":
    main()