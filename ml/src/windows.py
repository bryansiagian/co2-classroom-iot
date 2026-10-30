"""Langkah 5: bentuk jendela (N menit terakhir -> 15 menit ke depan) dan bagi data.

Prinsip:
- Input  : N baris terakhir semua fitur (skala z-score dari data train saja).
- Target : CO2 pada t+1 ... t+HORIZON (vektor 15 nilai). Nilai t+15 = elemen terakhir.
- Jendela yang memuat NaN (melewati celah) dibuang.
- Split kronologis 70/15/15 berdasarkan baris waktu. Sebuah jendela hanya masuk ke
  satu split jika SELURUH barisnya (input + target) berada di dalam rentang split itu,
  sehingga tidak ada kebocoran antar split.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config


@dataclass
class Scaler:
    features: list[str]
    mean: np.ndarray
    std: np.ndarray

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self.std

    def inverse_target(self, y: np.ndarray) -> np.ndarray:
        i = self.features.index(config.TARGET)
        return y * self.std[i] + self.mean[i]

    def to_json(self) -> dict:
        return {
            "features": self.features,
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
        }

    @staticmethod
    def from_json(d: dict) -> "Scaler":
        return Scaler(d["features"], np.array(d["mean"]), np.array(d["std"]))

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> "Scaler":
        return Scaler.from_json(json.loads(Path(path).read_text(encoding="utf-8")))


def select_features(df: pd.DataFrame) -> list[str]:
    """Fitur = kolom kontrak yang ada di data dan punya nilai (bukan kosong semua)."""
    feats = [c for c in config.FEATURE_CANDIDATES if c in df.columns and df[c].notna().any()]
    if config.TARGET not in feats:
        raise SystemExit("Kolom target co2_ppm tidak tersedia.")
    return feats


def split_bounds(n_rows: int, split=config.SPLIT) -> dict[str, tuple[int, int]]:
    """Batas baris [mulai, akhir) untuk train/val/test."""
    a = int(n_rows * split[0])
    b = int(n_rows * (split[0] + split[1]))
    return {"train": (0, a), "val": (a, b), "test": (b, n_rows)}


def fit_scaler(df: pd.DataFrame, features: list[str], train_range: tuple[int, int]) -> Scaler:
    tr = df.iloc[train_range[0] : train_range[1]][features]
    mean = tr.mean().to_numpy(dtype=float)
    std = tr.std().to_numpy(dtype=float)
    std = np.where(std < 1e-8, 1.0, std)  # hindari bagi nol (mis. PIR konstan)
    return Scaler(features, mean, std)


def make_windows(
    df: pd.DataFrame,
    features: list[str],
    scaler: Scaler,
    window: int,
    horizon: int = config.HORIZON,
    row_range: tuple[int, int] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Kembalikan (X, Y, Y_raw, t_end).

    X      : [n, window, n_fitur]  (terskala)
    Y      : [n, horizon]          (CO2 terskala)
    Y_raw  : [n, horizon]          (CO2 ppm asli)
    t_end  : [n] timestamp baris terakhir input (waktu 't')
    """
    lo, hi = row_range if row_range else (0, len(df))
    sub = df.iloc[lo:hi]
    vals = sub[features].to_numpy(dtype=float)
    ts = sub["timestamp"].to_numpy()
    n = len(sub)
    ti = features.index(config.TARGET)

    invalid = np.isnan(vals).any(axis=1).astype(int)
    csum = np.concatenate([[0], np.cumsum(invalid)])

    scaled = scaler.transform(vals)
    xs, ys, yr, te = [], [], [], []
    # i = indeks baris terakhir input; butuh baris i-window+1 ... i+horizon
    for i in range(window - 1, n - horizon):
        a, b = i - window + 1, i + horizon + 1
        if csum[b] - csum[a] != 0:
            continue
        xs.append(scaled[a : i + 1])
        ys.append(scaled[i + 1 : b, ti])
        yr.append(vals[i + 1 : b, ti])
        te.append(ts[i])
    if not xs:
        return (
            np.empty((0, window, len(features))),
            np.empty((0, horizon)),
            np.empty((0, horizon)),
            np.empty((0,), dtype="datetime64[ns]"),
        )
    return np.array(xs, dtype=np.float32), np.array(ys, dtype=np.float32), np.array(yr), np.array(te)
