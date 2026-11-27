
"""
Windowing dan scaling untuk prediksi CO2.

Input  : N timestep terakhir dari seluruh fitur.
Target : CO2 pada t+1 sampai t+HORIZON.
Split  : Kronologis train/validation/test.

Scaler:
- Menggunakan Min-Max Scaling.
- Parameter min dan max hanya dihitung dari data train.
- Window yang mengandung NaN atau inf dibuang.
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
    """Min-Max scaler untuk seluruh fitur."""

    features: list[str]
    data_min: np.ndarray
    data_range: np.ndarray

    def transform(self, x: np.ndarray) -> np.ndarray:
        """Mengubah data ke skala Min-Max."""
        x = np.asarray(x, dtype=float)

        if x.shape[-1] != len(self.features):
            raise ValueError(
                f"Jumlah fitur tidak sesuai. "
                f"Diharapkan {len(self.features)}, ditemukan {x.shape[-1]}."
            )

        return (x - self.data_min) / self.data_range

    def inverse_target(self, y: np.ndarray) -> np.ndarray:
        """Mengembalikan prediksi target ke satuan asli, yaitu ppm."""
        if config.TARGET not in self.features:
            raise ValueError(
                f"Target {config.TARGET} tidak ditemukan dalam scaler."
            )

        target_idx = self.features.index(config.TARGET)

        return (
            np.asarray(y, dtype=float) * self.data_range[target_idx]
            + self.data_min[target_idx]
        )

    def to_json(self) -> dict:
        """Mengubah parameter scaler menjadi dictionary."""
        return {
            "type": "minmax",
            "features": self.features,
            "data_min": self.data_min.tolist(),
            "data_range": self.data_range.tolist(),
        }

    @staticmethod
    def from_json(data: dict) -> "Scaler":
        """Membaca parameter scaler dari dictionary."""
        if data.get("type") != "minmax":
            raise ValueError(
                "Format scaler bukan Min-Max Scaling. "
                "Scaler lama mungkin menggunakan mean/std. "
                "Latih ulang model menggunakan scaler yang baru."
            )

        features = data["features"]
        data_min = np.asarray(data["data_min"], dtype=float)
        data_range = np.asarray(data["data_range"], dtype=float)

        if len(features) != len(data_min) or len(features) != len(data_range):
            raise ValueError("Dimensi parameter scaler tidak sesuai.")

        if not np.all(np.isfinite(data_min)):
            raise ValueError("data_min mengandung nilai tidak valid.")

        if not np.all(np.isfinite(data_range)) or np.any(data_range <= 0):
            raise ValueError("data_range mengandung nilai tidak valid.")

        return Scaler(features, data_min, data_range)

    def save(self, path: str | Path) -> None:
        """Menyimpan scaler ke file JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as file:
            json.dump(self.to_json(), file, indent=2)

    @staticmethod
    def load(path: str | Path) -> "Scaler":
        """Memuat scaler dari file JSON."""
        path = Path(path)

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return Scaler.from_json(data)


def select_features(df: pd.DataFrame) -> list[str]:
    """
    Memilih fitur yang tersedia dan memiliki minimal satu
    nilai numerik finite.

    Fitur yang seluruh nilainya kosong atau tidak valid
    tidak digunakan.
    """
    features = []

    for col in config.FEATURE_CANDIDATES:
        if col not in df.columns:
            continue

        values = pd.to_numeric(df[col], errors="coerce").to_numpy(
            dtype=float
        )

        if np.isfinite(values).any():
            features.append(col)

    if config.TARGET not in features:
        raise SystemExit(
            f"Kolom target {config.TARGET} tidak tersedia "
            "atau tidak memiliki nilai numerik valid."
        )

    return features


def split_bounds(
    n_rows: int,
    split=config.SPLIT
) -> dict[str, tuple[int, int]]:
    """
    Membagi data secara kronologis.

    Menghasilkan batas indeks [mulai, akhir):
    train, validation, dan test.
    """
    if n_rows <= 0:
        raise ValueError("Jumlah baris dataset harus lebih dari 0.")

    if len(split) != 3 or not np.isclose(sum(split), 1.0):
        raise ValueError("Proporsi split harus berjumlah 1.")

    if any(value <= 0 for value in split):
        raise ValueError("Setiap proporsi split harus lebih dari 0.")

    train_end = int(n_rows * split[0])
    val_end = int(n_rows * (split[0] + split[1]))

    if not (0 < train_end < val_end < n_rows):
        raise ValueError(
            "Jumlah data terlalu sedikit untuk pembagian train/val/test."
        )

    return {
        "train": (0, train_end),
        "val": (train_end, val_end),
        "test": (val_end, n_rows),
    }


def split_bounds_by_date(
    df: pd.DataFrame,
    val_start: str,
    test_start: str
) -> dict[str, tuple[int, int]]:
    """
    Membagi data berdasarkan tanggal.

    Train : sebelum val_start.
    Val   : val_start sampai sebelum test_start.
    Test  : mulai test_start.
    """
    if "timestamp" not in df.columns:
        raise ValueError("Kolom timestamp tidak tersedia.")

    ts = pd.to_datetime(df["timestamp"])

    val_timestamp = pd.Timestamp(val_start)
    test_timestamp = pd.Timestamp(test_start)

    val_idx = int(ts.searchsorted(val_timestamp))
    test_idx = int(ts.searchsorted(test_timestamp))

    n_rows = len(df)

    if not (0 < val_idx < test_idx < n_rows):
        raise SystemExit(
            f"Tanggal split tidak valid: "
            f"val_start={val_start}, test_start={test_start}. "
            f"Data mencakup {ts.iloc[0]} sampai {ts.iloc[-1]}."
        )

    return {
        "train": (0, val_idx),
        "val": (val_idx, test_idx),
        "test": (test_idx, n_rows),
    }


def fit_scaler(
    df: pd.DataFrame,
    features: list[str],
    train_range: tuple[int, int]
) -> Scaler:
    """
    Menghitung parameter Min-Max hanya dari data training.

    Rumus:
        X_scaled = (X - X_min) / (X_max - X_min)

    Jika fitur konstan, data_range diganti menjadi 1
    untuk menghindari pembagian dengan nol.
    """
    lo, hi = train_range

    if not (0 <= lo < hi <= len(df)):
        raise ValueError(f"Rentang training tidak valid: {train_range}")

    missing = [col for col in features if col not in df.columns]

    if missing:
        raise ValueError(f"Kolom fitur tidak ditemukan: {missing}")

    train_data = df.iloc[lo:hi][features].apply(
        pd.to_numeric,
        errors="coerce"
    )

    train_values = train_data.to_numpy(dtype=float)

    data_min = []
    data_range = []

    for idx, feature in enumerate(features):
        values = train_values[:, idx]
        valid_values = values[np.isfinite(values)]

        if len(valid_values) == 0:
            raise ValueError(
                f"Fitur {feature} tidak memiliki nilai valid "
                "pada data training."
            )

        minimum = float(np.min(valid_values))
        maximum = float(np.max(valid_values))

        feature_range = maximum - minimum

        if feature_range < 1e-8:
            feature_range = 1.0

        data_min.append(minimum)
        data_range.append(feature_range)

    return Scaler(
        features=features,
        data_min=np.asarray(data_min, dtype=float),
        data_range=np.asarray(data_range, dtype=float),
    )


def make_windows(
    df: pd.DataFrame,
    features: list[str],
    scaler: Scaler,
    window: int,
    horizon: int = config.HORIZON,
    row_range: tuple[int, int] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Membentuk sequence untuk training dan evaluasi.

    X:
        [jumlah_sampel, window, jumlah_fitur]

    Y:
        [jumlah_sampel, horizon] dalam skala Min-Max.

    Y_raw:
        [jumlah_sampel, horizon] dalam ppm asli.

    t_end:
        Timestamp pada baris terakhir input.

    Window yang mengandung NaN atau inf akan dibuang.
    """
    if window <= 0 or horizon <= 0:
        raise ValueError("window dan horizon harus lebih dari 0.")

    if features != scaler.features:
        raise ValueError(
            "Urutan fitur pada make_windows harus sama "
            "dengan urutan fitur pada scaler."
        )

    if config.TARGET not in features:
        raise ValueError(
            f"Target {config.TARGET} tidak ditemukan dalam fitur."
        )

    if "timestamp" not in df.columns:
        raise ValueError("Kolom timestamp tidak tersedia.")

    if row_range is None:
        lo, hi = 0, len(df)
    else:
        lo, hi = row_range

    if not (0 <= lo < hi <= len(df)):
        raise ValueError(f"row_range tidak valid: {row_range}")

    sub = df.iloc[lo:hi]

    # Konversi fitur ke numerik.
    values = sub[features].apply(
        pd.to_numeric,
        errors="coerce"
    ).to_numpy(dtype=float)

    timestamps = pd.to_datetime(sub["timestamp"]).to_numpy()

    n_rows = len(sub)
    target_idx = features.index(config.TARGET)

    # Baris dianggap invalid jika memiliki NaN atau infinity
    # pada salah satu fitur yang digunakan.
    invalid = (~np.isfinite(values)).any(axis=1).astype(int)

    # Cumulative sum untuk mengecek invalid row secara efisien.
    csum = np.concatenate([
        np.array([0], dtype=int),
        np.cumsum(invalid)
    ])

    # Scaling menggunakan parameter dari training.
    scaled = scaler.transform(values)

    xs = []
    ys = []
    y_raw = []
    t_end = []

    # i adalah indeks terakhir input.
    # Input : i-window+1 sampai i.
    # Target: i+1 sampai i+horizon.
    for i in range(window - 1, n_rows - horizon):

        start = i - window + 1
        end = i + horizon + 1

        # Buang window jika ada NaN atau infinity
        # pada input maupun target.
        if csum[end] - csum[start] > 0:
            continue

        xs.append(scaled[start:i + 1])

        ys.append(
            scaled[i + 1:end, target_idx]
        )

        y_raw.append(
            values[i + 1:end, target_idx]
        )

        t_end.append(timestamps[i])

    # Jika tidak ada window valid.
    if not xs:
        return (
            np.empty(
                (0, window, len(features)),
                dtype=np.float32
            ),
            np.empty(
                (0, horizon),
                dtype=np.float32
            ),
            np.empty(
                (0, horizon),
                dtype=np.float32
            ),
            np.empty(
                (0,),
                dtype="datetime64[ns]"
            ),
        )

    return (
        np.asarray(xs, dtype=np.float32),
        np.asarray(ys, dtype=np.float32),
        np.asarray(y_raw, dtype=np.float32),
        np.asarray(t_end),
    )
