"""Menerima pesan sensor: validasi, simpan, prediksi, rekomendasi.

Aturan validasi mengikuti docs/02-kontrak-data.md bagian 2. Pesan mentah selalu disimpan;
nilai yang tidak valid hanya ditandai, tidak dibuang.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Callable

from .config import Settings
from .db import Database
from .predictor import Predictor
from .recommend import recommend
from .timeutil import parse_iso, to_iso, utcnow

log = logging.getLogger("co2class.ingest")

CO2_RANGE = (350, 5000)
TEMP_RANGE = (-10, 60)
HUM_RANGE = (0, 100)
HISTORY_FOR_PREDICTOR = 60  # menit

Publisher = Callable[[str, dict], None]


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    return v if isinstance(v, (int, float)) else None


def _in(v, rng) -> bool:
    return v is None or rng[0] <= v <= rng[1]


class Pipeline:
    def __init__(self, db: Database, settings: Settings, predictor: Predictor,
                 publisher: Publisher | None = None):
        self.db = db
        self.s = settings
        self.predictor = predictor
        self.publisher = publisher
        self._last_seq: dict[str, int] = {}

    # ------------------------------------------------------------------ ingest
    def handle_sensor_message(self, room_id: str, payload: bytes | str | dict,
                              received_at: datetime | None = None) -> dict | None:
        received_at = received_at or utcnow()
        raw = payload if isinstance(payload, str) else (
            payload.decode("utf-8", "replace") if isinstance(payload, bytes) else json.dumps(payload))
        try:
            msg = json.loads(raw)
            if not isinstance(msg, dict) or not msg.get("device_id"):
                raise ValueError("device_id wajib ada")
        except (ValueError, TypeError) as e:
            log.warning("Pesan sensor ditolak (%s): %.120s", e, raw)
            return None

        flags: list[str] = []
        co2 = _num(msg.get("co2_ppm"))
        t_in, h_in = _num(msg.get("temp_in_c")), _num(msg.get("hum_in_pct"))
        t_out, h_out = _num(msg.get("temp_out_c")), _num(msg.get("hum_out_pct"))
        if not (_in(co2, CO2_RANGE) and _in(t_in, TEMP_RANGE) and _in(t_out, TEMP_RANGE)
                and _in(h_in, HUM_RANGE) and _in(h_out, HUM_RANGE)):
            flags.append("suspect")

        ts = self._effective_ts(msg.get("ts"), received_at, flags)
        pir = msg.get("pir")
        pir = int(pir) if pir in (0, 1, True, False) else None
        faults = msg.get("faults") if isinstance(msg.get("faults"), list) else []
        seq = msg.get("seq") if isinstance(msg.get("seq"), int) else None
        self._check_seq(msg["device_id"], seq)

        row = (
            room_id, msg["device_id"], seq, to_iso(ts), to_iso(received_at),
            int(round(co2)) if co2 is not None else None, t_in, h_in, t_out, h_out,
            pir, _num(msg.get("rssi")), json.dumps(faults), json.dumps(flags), raw,
        )
        try:
            self.db.execute(
                """INSERT INTO sensor_reading (room_id, device_id, seq, ts_utc, received_at, co2_ppm,
                   temp_in_c, hum_in_pct, temp_out_c, hum_out_pct, pir, rssi, faults, quality_flags, raw)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
        except sqlite3.IntegrityError:
            log.info("Pesan duplikat diabaikan (device=%s seq=%s)", msg["device_id"], seq)
            return None

        result = {"room_id": room_id, "ts": to_iso(ts), "flags": flags, "co2_ppm": co2}
        if co2 is not None and "suspect" not in flags:
            result["recommendation"] = self._predict_and_recommend(room_id, to_iso(ts), ts)
        return result

    def _effective_ts(self, ts_raw, received_at: datetime, flags: list[str]) -> datetime:
        try:
            ts = parse_iso(ts_raw) if isinstance(ts_raw, str) else None
        except ValueError:
            ts = None
        if ts is None or abs((ts - received_at).total_seconds()) > self.s.ts_tolerance_s:
            flags.append("ts_corrected")
            return received_at
        return ts

    def _check_seq(self, device_id: str, seq: int | None) -> None:
        if seq is None:
            return
        last = self._last_seq.get(device_id)
        if last is not None and seq > last + 1:
            log.warning("Pesan hilang dari %s: seq %s -> %s", device_id, last, seq)
        self._last_seq[device_id] = seq

    # -------------------------------------------------------- predict/recommend
    def recent_co2(self, room_id: str, limit: int = HISTORY_FOR_PREDICTOR) -> list[float]:
        rows = self.db.query(
            """SELECT co2_ppm FROM sensor_reading
               WHERE room_id=? AND co2_ppm IS NOT NULL AND quality_flags NOT LIKE '%suspect%'
               ORDER BY ts_utc DESC, id DESC LIMIT ?""", (room_id, limit))
        return [float(r["co2_ppm"]) for r in reversed(rows)]

    def _predict_and_recommend(self, room_id: str, created_at: str, ts: datetime) -> dict:
        forecast = self.predictor.predict(self.recent_co2(room_id))
        rec = recommend(forecast, self.s)
        self.db.executemany(
            "INSERT INTO prediction (room_id, created_at, target_ts, horizon_min, co2_ppm, model) VALUES (?,?,?,?,?,?)",
            [(room_id, created_at, to_iso(ts + timedelta(minutes=k)), k, v, self.predictor.name)
             for k, v in enumerate(forecast, start=1)])
        self.db.execute(
            """INSERT INTO recommendation (room_id, created_at, action, minutes, predicted_peak_ppm,
               predicted_at_15min_ppm, model) VALUES (?,?,?,?,?,?,?)""",
            (room_id, created_at, rec.action, rec.minutes, rec.peak, rec.at15, self.predictor.name))
        payload = {
            "v": 1, "ts": created_at, "action": rec.action, "minutes": rec.minutes,
            "predicted_peak_ppm": round(rec.peak), "predicted_at_15min_ppm": round(rec.at15),
            "model": self.predictor.name,
        }
        if self.publisher:
            try:
                self.publisher(room_id, payload)
            except Exception:  # jangan sampai kegagalan MQTT menghentikan penyimpanan
                log.exception("Gagal mengirim rekomendasi ke MQTT")
        return payload
