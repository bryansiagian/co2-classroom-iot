
"""
Langkah 8: Inferensi model GRU.

Dipakai oleh backend (GRUPredictor).

Cara pakai:
    from src.predict import GRUModel

    model = GRUModel.load("models/demo/gru", mode="demo")
    output = model.predict(df_recent)

    output["t+15"]

Input:
    DataFrame minimal berisi:
    - timestamp
    - seluruh fitur yang digunakan saat training

Output:
    Dictionary prediksi CO2 untuk t+1 sampai t+horizon.

Validasi:
    - Memeriksa kelengkapan kolom.
    - Memeriksa jumlah baris.
    - Memeriksa timestamp.
    - Memeriksa celah waktu.
    - Memeriksa urutan timestamp.
    - Menolak NaN dan infinity.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from . import config
from .guard import assert_meta_matches, assert_mode_safe
from .models import RNNForecaster
from .windows import Scaler


# Ambang maksimum celah waktu antarbaris.
# Samakan dengan kesepakatan tim dan kebijakan preprocessing.
MAX_GAP_MIN = 5


class GRUModel:
    """Class untuk memuat model GRU dan menghasilkan prediksi CO2."""

    def __init__(
        self,
        net: RNNForecaster,
        scaler: Scaler,
        meta: dict
    ):
        self.net = net.eval()
        self.scaler = scaler
        self.meta = meta

        self.window = int(meta["window"])
        self.features = list(meta["features"])
        self.horizon = int(meta["horizon"])

    @classmethod
    def load(
        cls,
        model_dir: str | Path,
        mode: str
    ) -> "GRUModel":
        """
        Memuat model, scaler, dan metadata.

        mode:
            demo atau real
        """
        directory = Path(model_dir)

        # Pemeriksaan keamanan pemisahan mode.
        assert_mode_safe(mode, directory)

        # Memastikan metadata sesuai dengan mode.
        assert_meta_matches(mode, directory / "meta.json")

        # Membaca metadata model.
        meta = json.loads(
            (directory / "meta.json").read_text(encoding="utf-8")
        )

        # Membuat ulang arsitektur GRU sesuai metadata.
        net = RNNForecaster(
            n_features=len(meta["features"]),
            kind=meta["kind"],
            hidden=meta["hidden"],
            layers=meta["layers"],
            dropout=meta["dropout"],
            horizon=meta["horizon"],
        )

        # Memuat bobot model.
        state_dict = torch.load(
            directory / "model.pt",
            map_location="cpu"
        )

        net.load_state_dict(state_dict)
        net.eval()

        # Memuat scaler yang digunakan saat training.
        scaler = Scaler.load(directory / "scaler.json")

        # Memastikan fitur model dan scaler konsisten.
        if scaler.features != list(meta["features"]):
            raise ValueError(
                "Fitur pada scaler.json tidak sesuai dengan meta.json."
            )

        return cls(net, scaler, meta)

    def predict(self, recent: pd.DataFrame) -> dict[str, float]:
        """
        Menghasilkan prediksi CO2 berdasarkan data terbaru.

        recent:
            DataFrame berisi data sensor historis.

        Return:
            {
                "t+1": nilai_prediksi,
                "t+2": nilai_prediksi,
                ...
                "t+15": nilai_prediksi
            }
        """

        # 1. Pastikan seluruh fitur tersedia.
        missing = [
            col for col in self.features
            if col not in recent.columns
        ]

        if missing:
            raise ValueError(
                f"Kolom fitur hilang: {missing}"
            )

        # 2. Timestamp wajib tersedia.
        if "timestamp" not in recent.columns:
            raise ValueError(
                "Kolom timestamp wajib tersedia "
                "untuk memeriksa celah waktu."
            )

        # 3. Pastikan jumlah baris mencukupi.
        if len(recent) < self.window:
            raise ValueError(
                f"Butuh minimal {self.window} baris, "
                f"tersedia {len(recent)}."
            )

        # 4. Ambil data sebanyak window terakhir.
        win = recent.tail(self.window).copy()

        # 5. Konversi timestamp.
        ts = pd.to_datetime(
            win["timestamp"],
            errors="coerce"
        )

        # Tolak timestamp yang tidak valid.
        if ts.isna().any():
            raise ValueError(
                "Timestamp mengandung nilai kosong "
                "atau format tidak valid."
            )

        # 6. Hitung selisih waktu antarbaris.
        gaps = ts.diff().dropna()

        # 7. Pastikan timestamp berurutan.
        if (gaps <= pd.Timedelta(0)).any():
            raise ValueError(
                "Timestamp tidak berurutan "
                "atau terdapat timestamp duplikat."
            )

        # 8. Periksa celah waktu.
        if (
            gaps > pd.Timedelta(minutes=MAX_GAP_MIN)
        ).any():

            longest = (
                gaps.max().total_seconds() / 60.0
            )

            raise ValueError(
                f"Riwayat bercelah {longest:.0f} menit "
                f"(> {MAX_GAP_MIN} menit); "
                "prediksi tidak dihasilkan."
            )

        # 9. Ambil nilai fitur dan konversi ke numerik.
        x = win[self.features].apply(
            pd.to_numeric,
            errors="coerce"
        ).to_numpy(dtype=float)

        # 10. Tolak NaN dan infinity.
        if not np.isfinite(x).all():
            raise ValueError(
                "Jendela masih memuat NaN atau infinity. "
                "Data harus dirapikan terlebih dahulu."
            )

        # 11. Normalisasi menggunakan scaler training.
        x_scaled = self.scaler.transform(x)

        # 12. Tambahkan dimensi batch.
        x_tensor = torch.from_numpy(
            x_scaled[None].astype(np.float32)
        )

        # 13. Jalankan inferensi.
        self.net.eval()

        with torch.no_grad():
            prediction_scaled = self.net(x_tensor).cpu().numpy()

        # 14. Kembalikan hasil prediksi ke satuan ppm.
        prediction_ppm = self.scaler.inverse_target(
            prediction_scaled
        )[0]

        # 15. Pastikan hasil prediksi valid.
        if not np.isfinite(prediction_ppm).all():
            raise ValueError(
                "Model menghasilkan prediksi NaN atau infinity."
            )

        # 16. Bentuk dictionary hasil prediksi.
        return {
            f"t+{k + 1}": float(value)
            for k, value in enumerate(prediction_ppm)
        }
