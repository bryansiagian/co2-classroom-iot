"""Langkah 8: inferensi. Dipakai oleh backend (GRUPredictor).

Cara pakai (contoh):
    from src.predict import GRUModel
    m = GRUModel.load("models/demo/gru", mode="demo")
    out = m.predict(df_recent)   # df_recent: >= window baris, 1 baris = 1 menit
    out["t+15"]                  # prediksi CO2 15 menit ke depan (ppm)

Catatan: model dilatih pada grid 1 menit tanpa NaN. Pastikan backend memberi
jendela terakhir yang sudah dirapikan (agregasi 1 menit, celah pendek diisi).
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


class GRUModel:
    def __init__(self, net: RNNForecaster, scaler: Scaler, meta: dict):
        self.net, self.scaler, self.meta = net.eval(), scaler, meta
        self.window = int(meta["window"])
        self.features = list(meta["features"])

    @classmethod
    def load(cls, model_dir: str | Path, mode: str) -> "GRUModel":
        d = Path(model_dir)
        assert_mode_safe(mode, d)
        assert_meta_matches(mode, d / "meta.json")
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        net = RNNForecaster(
            n_features=len(meta["features"]),
            kind=meta["kind"],
            hidden=meta["hidden"],
            layers=meta["layers"],
            dropout=meta["dropout"],
            horizon=meta["horizon"],
        )
        net.load_state_dict(torch.load(d / "model.pt", map_location="cpu"))
        return cls(net, Scaler.load(d / "scaler.json"), meta)

    def predict(self, recent: pd.DataFrame) -> dict[str, float]:
        missing = [c for c in self.features if c not in recent.columns]
        if missing:
            raise ValueError(f"Kolom hilang: {missing}")
        if len(recent) < self.window:
            raise ValueError(f"Butuh minimal {self.window} baris, tersedia {len(recent)}")
        x = recent[self.features].tail(self.window).to_numpy(dtype=float)
        if np.isnan(x).any():
            raise ValueError("Jendela masih memuat NaN; isi/rapikan dulu.")
        xt = torch.from_numpy(self.scaler.transform(x)[None].astype(np.float32))
        with torch.no_grad():
            y = self.net(xt).numpy()
        ppm = self.scaler.inverse_target(y)[0]
        return {f"t+{k + 1}": float(v) for k, v in enumerate(ppm)}
