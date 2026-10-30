"""Metrik regresi: MAE, RMSE, R2 (keseluruhan, t+15, dan per langkah horizon)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def mae(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean(np.abs(y - p)))


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - p) ** 2)))


def r2(y: np.ndarray, p: np.ndarray) -> float:
    ss_res = float(np.sum((y - p) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")


def summary(y: np.ndarray, p: np.ndarray) -> dict:
    """y, p: [n, horizon] dalam ppm. Kembalikan metrik pada t+15 dan rata-rata semua langkah."""
    return {
        "MAE_t15": mae(y[:, -1], p[:, -1]),
        "RMSE_t15": rmse(y[:, -1], p[:, -1]),
        "R2_t15": r2(y[:, -1], p[:, -1]),
        "MAE_all": mae(y, p),
        "RMSE_all": rmse(y, p),
    }


def per_horizon(y: np.ndarray, p: np.ndarray) -> pd.DataFrame:
    rows = []
    for k in range(y.shape[1]):
        rows.append(
            {
                "step": f"t+{k + 1}",
                "MAE": mae(y[:, k], p[:, k]),
                "RMSE": rmse(y[:, k], p[:, k]),
                "R2": r2(y[:, k], p[:, k]),
            }
        )
    return pd.DataFrame(rows)
