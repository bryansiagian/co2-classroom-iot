"""Langkah 2: muat dataset mentah (CSV/XLSX) dan petakan kolom ke kontrak data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import config
from .guard import assert_mode_safe

SUPPORTED = (".csv", ".xlsx", ".xls")


def find_raw_file(raw_dir: Path, explicit: str | None = None) -> Path:
    if explicit:
        f = Path(explicit)
        if not f.exists():
            raise SystemExit(f"Berkas tidak ditemukan: {f}")
        return f
    files = sorted(p for p in raw_dir.iterdir() if p.suffix.lower() in SUPPORTED)
    if not files:
        raise SystemExit(
            f"Tidak ada CSV/XLSX di {raw_dir}. Taruh dataset di sana, "
            "atau jalankan: python -m src.make_demo_data"
        )
    if len(files) > 1:
        print(f"[peringatan] ada {len(files)} berkas, memakai yang pertama: {files[0].name}")
    return files[0]


def read_raw(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        # sep=None -> deteksi otomatis (koma / titik koma)
        return pd.read_csv(path, sep=None, engine="python")
    return pd.read_excel(path)


def load_column_map(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_mapping(raw: pd.DataFrame, cmap: dict) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Kembalikan (df berkolom kontrak, kolom_hilang, kolom_dibuang_dari_fitur)."""
    out = pd.DataFrame()
    missing: list[str] = []
    for col in config.CONTRACT_COLS:
        src = cmap.get(col)
        if src is None:
            missing.append(col)
            continue
        if src not in raw.columns:
            raise SystemExit(
                f"Kolom '{src}' (untuk '{col}') tidak ada di dataset. "
                f"Kolom tersedia: {list(raw.columns)}. Perbaiki column_map.json."
            )
        out[col] = raw[src]
    for must in ("timestamp", config.TARGET):
        if must in missing:
            raise SystemExit(f"Kolom wajib '{must}' belum dipetakan di column_map.json.")

    out["timestamp"] = pd.to_datetime(
        out["timestamp"], format=cmap.get("_timestamp_format"), errors="coerce"
    )
    tz = cmap.get("_timezone")
    if tz:
        out["timestamp"] = out["timestamp"].dt.tz_localize(tz).dt.tz_convert(None)
    n_bad_ts = int(out["timestamp"].isna().sum())
    if n_bad_ts:
        print(f"[peringatan] {n_bad_ts} baris timestamp tidak terbaca, dibuang.")
        out = out.dropna(subset=["timestamp"])
    for col in out.columns:
        if col != "timestamp":
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out, missing, [c for c in config.FEATURE_CANDIDATES if c in missing]


def load_mapped(mode: str, file: str | None = None) -> tuple[pd.DataFrame, Path, list[str]]:
    p = config.paths(mode)
    raw_path = find_raw_file(p["raw_dir"], file)
    assert_mode_safe(mode, raw_path)
    raw = read_raw(raw_path)
    cmap = load_column_map(p["column_map"])
    df, missing, _ = apply_mapping(raw, cmap)
    return df, raw_path, missing


def main() -> None:
    ap = argparse.ArgumentParser(description="Muat dataset dan cek pemetaan kolom")
    ap.add_argument("--mode", default=None)
    ap.add_argument("--file", default=None)
    a = ap.parse_args()
    mode = config.get_mode(a.mode)
    df, raw_path, missing = load_mapped(mode, a.file)
    print(f"Mode        : {mode}")
    print(f"Berkas      : {raw_path}")
    print(f"Baris       : {len(df)}")
    print(f"Rentang     : {df['timestamp'].min()} -> {df['timestamp'].max()}")
    print(f"Kolom ada   : {[c for c in df.columns]}")
    print(f"Kolom absen : {missing}")
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
