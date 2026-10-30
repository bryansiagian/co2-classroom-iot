"""Langkah 6: model. Persistence (garis dasar), LSTM, dan GRU (PyTorch)."""
from __future__ import annotations

import numpy as np
import torch
from torch import nn

from . import config


class Persistence:
    """Prediksi CO2 t+k = CO2 terakhir yang teramati (untuk semua k)."""

    name = "persistence"

    def __init__(self, target_index: int, horizon: int = config.HORIZON):
        self.ti = target_index
        self.h = horizon

    def predict(self, X: np.ndarray) -> np.ndarray:
        last = X[:, -1, self.ti]
        return np.repeat(last[:, None], self.h, axis=1)


class RNNForecaster(nn.Module):
    """RNN (LSTM/GRU) -> Linear(horizon). Keluaran: CO2 terskala untuk t+1..t+horizon."""

    def __init__(
        self,
        n_features: int,
        kind: str = "gru",
        hidden: int = 64,
        layers: int = 2,
        dropout: float = 0.2,
        horizon: int = config.HORIZON,
    ):
        super().__init__()
        kind = kind.lower()
        if kind not in {"lstm", "gru"}:
            raise ValueError("kind harus 'lstm' atau 'gru'")
        rnn_cls = nn.LSTM if kind == "lstm" else nn.GRU
        self.kind = kind
        self.rnn = rnn_cls(
            input_size=n_features,
            hidden_size=hidden,
            num_layers=layers,
            batch_first=True,
            dropout=dropout if layers > 1 else 0.0,
        )
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, horizon))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.rnn(x)
        return self.head(out[:, -1, :])


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
