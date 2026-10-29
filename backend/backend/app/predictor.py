"""Prediksi CO2 15 menit ke depan.

Antarmuka tunggal: Predictor.predict(history_ppm) -> 15 nilai (t+1 .. t+15 menit).
history_ppm adalah daftar CO2 terbaru, urut waktu, satu nilai per menit.

Model GRU dari ml/ nanti dipasang lewat GRUPredictor tanpa mengubah bagian lain.
"""
from __future__ import annotations

HORIZON = 15


class Predictor:
    name = "base"

    def predict(self, history_ppm: list[float]) -> list[float]:
        raise NotImplementedError


class PersistencePredictor(Predictor):
    """Cadangan sesuai docs: nilai terakhir dipertahankan. Juga pembanding wajib di evaluasi."""

    name = "persistence"

    def predict(self, history_ppm: list[float]) -> list[float]:
        return [float(history_ppm[-1])] * HORIZON


class LinearDemoPredictor(Predictor):
    """Ekstrapolasi tren 5 menit terakhir dengan peredaman. Hanya untuk demo dashboard, bukan hasil TA."""

    name = "linear-demo"

    def predict(self, history_ppm: list[float]) -> list[float]:
        last = history_ppm[-1]
        ref = history_ppm[-6] if len(history_ppm) >= 6 else history_ppm[0]
        steps = min(5, len(history_ppm) - 1) or 1
        slope = (last - ref) / steps
        out, acc = [], 0.0
        for k in range(1, HORIZON + 1):
            acc += 0.96**k
            out.append(max(400.0, last + slope * acc))
        return out


class GRUPredictor(Predictor):
    """TODO: muat model hasil pelatihan di ml/ dan lakukan inferensi.

    Hal yang perlu disepakati dengan ml/: panjang jendela masukan, fitur yang dipakai
    (CO2 saja atau plus suhu, kelembapan, PIR), skala normalisasi, dan format berkas model.
    """

    name = "gru-v1"

    def __init__(self, model_path: str):
        raise NotImplementedError("Model GRU belum dipasang. Pakai PREDICTOR=persistence untuk sementara.")


def build_predictor(kind: str, model_path: str = "") -> Predictor:
    kind = kind.lower()
    if kind == "persistence":
        return PersistencePredictor()
    if kind == "linear":
        return LinearDemoPredictor()
    if kind == "gru":
        return GRUPredictor(model_path)
    raise ValueError(f"PREDICTOR tidak dikenal: {kind}")
