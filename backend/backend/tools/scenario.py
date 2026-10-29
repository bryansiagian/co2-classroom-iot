"""Skenario simulasi satu kelas (siklus 150 menit) untuk data uji. BUKAN data pengukuran.

Dipakai oleh seed_db.py dan fake_publisher.py. Rumusnya sama dengan frontend/lib/mock.ts
sehingga tampilan data simulasi dan data dari backend mirip.
"""
import math

CYCLE = 150


def _noise(minute: int) -> float:
    x = math.sin(minute * 12.9898) * 43758.5453
    return (x - math.floor(x) - 0.5) * 24


def co2_at(minute: int) -> int:
    m = minute % CYCLE
    if m < 100:
        v = 520 + 800 * (1 - math.exp(-m / 60))
    elif m < 108:
        v100 = 520 + 800 * (1 - math.exp(-100 / 60))
        v = 560 + (v100 - 560) * math.exp(-(m - 100) / 3)
    else:
        v = 560 - (m - 108) * (40 / 42)
    return round(v + _noise(minute))


def occupied(minute: int) -> bool:
    return minute % CYCLE < 100


def sensor_message(minute: int, ts_iso: str | None, seq: int, device_id: str = "esp32-gd525-01") -> dict:
    co2 = co2_at(minute)
    msg = {
        "v": 1,
        "device_id": device_id,
        "seq": seq,
        "co2_ppm": co2,
        "temp_in_c": round(27.4 + (co2 - 520) / 800 * 1.6, 1),
        "hum_in_pct": 62.0,
        "temp_out_c": 24.8,
        "hum_out_pct": 78.0,
        "pir": 1 if occupied(minute) else 0,
        "rssi": -60,
        "faults": [],
    }
    if ts_iso:
        msg["ts"] = ts_iso
    return msg
