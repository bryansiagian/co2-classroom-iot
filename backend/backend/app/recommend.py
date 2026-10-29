"""Aturan rekomendasi (draf di docs/02-kontrak-data.md bagian 4).

Berdasarkan nilai tertinggi dari 15 prediksi ke depan. Ambang dapat diubah lewat konfigurasi.
"""
from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class Recommendation:
    action: str  # none | watch | flush
    minutes: int
    peak: float
    at15: float


def recommend(forecast: list[float], s: Settings) -> Recommendation:
    peak = max(forecast)
    at15 = forecast[-1]
    if peak >= s.th_high:
        if peak >= s.th_critical:
            minutes = 5
        elif peak >= 1150:
            minutes = 4
        else:
            minutes = 3
        return Recommendation("flush", minutes, peak, at15)
    if peak >= s.th_watch:
        return Recommendation("watch", 0, peak, at15)
    return Recommendation("none", 0, peak, at15)


def reason_for(action: str, peak: float, at15: float, th_high: float) -> str:
    high = f"{int(th_high):,}".replace(",", ".")
    if action == "flush":
        return (
            f"CO₂ diprediksi mencapai {round(peak)} ppm dalam 15 menit. "
            f"Buka jendela dan pintu sekarang agar tidak melewati {high} ppm."
        )
    if action == "watch":
        return (
            f"CO₂ diprediksi naik ke {round(peak)} ppm. "
            "Belum perlu ventilasi, tetapi bersiap jika tren berlanjut."
        )
    return "CO₂ diprediksi tetap rendah dalam 15 menit ke depan."
