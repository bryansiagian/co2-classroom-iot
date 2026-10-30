"""Konfigurasi terpusat untuk folder ml/.

DATA_MODE dibaca dari environment variable DATA_MODE (demo | real).
Bisa juga ditimpa lewat argumen --mode pada tiap skrip.
"""
from __future__ import annotations

import os
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]

# --- Kontrak data (harus sama dengan backend) -------------------------------
CONTRACT_COLS = [
    "timestamp",
    "co2_ppm",
    "temp_in_c",
    "hum_in_pct",
    "temp_out_c",
    "hum_out_pct",
    "pir",
]
TARGET = "co2_ppm"
# Kolom fitur kandidat (semua selain timestamp). Kolom yang tidak ada di
# dataset otomatis dibuang saat pemuatan.
FEATURE_CANDIDATES = [c for c in CONTRACT_COLS if c != "timestamp"]

# Rentang nilai valid (di luar rentang -> dianggap rusak -> NaN)
VALID_RANGE = {
    "co2_ppm": (250.0, 10000.0),
    "temp_in_c": (-10.0, 60.0),
    "hum_in_pct": (0.0, 100.0),
    "temp_out_c": (-10.0, 60.0),
    "hum_out_pct": (0.0, 100.0),
    "pir": (0.0, 1.0),
}

# --- Parameter pemodelan ----------------------------------------------------
STEP_MIN = 1            # resolusi data bersih (menit)
HORIZON = 15            # prediksi 1..15 menit ke depan
MAX_GAP_MIN = 3         # celah <= ini boleh diisi (interpolasi linear)
WINDOW_CANDIDATES = [15, 30, 60]
SPLIT = (0.70, 0.15, 0.15)
THRESHOLDS_PPM = [800, 1000, 1500]
SEED = 42


def get_mode(cli_mode: str | None = None) -> str:
    mode = (cli_mode or os.getenv("DATA_MODE", "demo")).strip().lower()
    if mode not in {"demo", "real"}:
        raise SystemExit(f"DATA_MODE tidak valid: {mode!r} (pilih demo atau real)")
    return mode


def paths(mode: str) -> dict[str, Path]:
    p = {
        "raw_dir": ML_ROOT / "data" / mode,
        "processed_dir": ML_ROOT / "data" / "processed" / mode,
        "models_dir": ML_ROOT / "models" / mode,
        "reports_dir": ML_ROOT / "reports" / mode,
        "column_map": ML_ROOT / "column_map.json",
    }
    for key in ("processed_dir", "models_dir", "reports_dir"):
        p[key].mkdir(parents=True, exist_ok=True)
    return p
