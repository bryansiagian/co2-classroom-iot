"""Menyusun JSON untuk GET /api/dashboard. Bentuknya harus sama dengan frontend/lib/types.ts."""
from __future__ import annotations

from .config import Settings
from .db import Database
from .predictor import HORIZON, Predictor
from .recommend import recommend, reason_for
from .timeutil import iso_to_ms, ms_to_iso

HISTORY_MINUTES = 360


def _latest_non_null(db: Database, room_id: str, column: str):
    rows = db.query(
        f"SELECT {column} AS v FROM sensor_reading WHERE room_id=? AND {column} IS NOT NULL "
        "ORDER BY ts_utc DESC, id DESC LIMIT 1", (room_id,))
    return rows[0]["v"] if rows else None


def _history(db: Database, room_id: str) -> list[dict]:
    rows = db.query(
        """SELECT ts_utc, co2_ppm FROM sensor_reading
           WHERE room_id=? AND co2_ppm IS NOT NULL AND quality_flags NOT LIKE '%suspect%'
           ORDER BY ts_utc DESC, id DESC LIMIT ?""", (room_id, HISTORY_MINUTES))
    return [{"t": iso_to_ms(r["ts_utc"]), "co2": r["co2_ppm"]} for r in reversed(rows)]


def _stored_forecast(db: Database, room_id: str) -> tuple[list[dict], str] | None:
    head = db.query("SELECT created_at, model FROM prediction WHERE room_id=? ORDER BY created_at DESC, id DESC LIMIT 1",
                    (room_id,))
    if not head:
        return None
    rows = db.query(
        "SELECT target_ts, co2_ppm FROM prediction WHERE room_id=? AND created_at=? AND model=? "
        "ORDER BY horizon_min", (room_id, head[0]["created_at"], head[0]["model"]))
    if len(rows) != HORIZON:
        return None
    return [{"t": iso_to_ms(r["target_ts"]), "co2": round(r["co2_ppm"])} for r in rows], head[0]["model"]


def _events(history: list[dict], s: Settings) -> list[dict]:
    events: list[dict] = []

    def dropping(j: int) -> bool:
        return j >= 3 and history[j - 3]["co2"] - history[j]["co2"] > 120

    for i in range(1, len(history)):
        a, b, t = history[i - 1]["co2"], history[i]["co2"], history[i]["t"]
        if a < s.th_high <= b:
            events.append({"t": t, "text": f"CO₂ melewati {int(s.th_high):,} ppm".replace(",", "."), "level": "high"})
        elif a < s.th_watch <= b:
            events.append({"t": t, "text": f"CO₂ melewati {int(s.th_watch)} ppm", "level": "watch"})
        if dropping(i) and not dropping(i - 1):
            events.append({"t": t, "text": "CO₂ turun cepat, ventilasi diduga dibuka", "level": "good"})
    return list(reversed(events))[:5]


def build_dashboard(db: Database, s: Settings, predictor: Predictor, room_id: str) -> dict | None:
    history = _history(db, room_id)
    if not history:
        return None
    last = history[-1]

    stored = _stored_forecast(db, room_id)
    if stored:
        forecast, _model = stored
    else:  # belum ada prediksi tersimpan: hitung langsung
        values = predictor.predict([float(p["co2"]) for p in history[-60:]])
        forecast = [{"t": last["t"] + k * 60_000, "co2": round(v)} for k, v in enumerate(values, start=1)]

    rec = recommend([float(p["co2"]) for p in forecast], s)

    pir_rows = db.query(
        "SELECT 1 FROM sensor_reading WHERE room_id=? AND pir=1 AND ts_utc > ? LIMIT 1",
        (room_id, _minus_minutes(last["t"], 5)))

    return {
        "room": s.room_label,
        "updatedAt": last["t"],
        "current": {
            "co2": last["co2"],
            "tempIn": _latest_non_null(db, room_id, "temp_in_c"),
            "humIn": _latest_non_null(db, room_id, "hum_in_pct"),
            "tempOut": _latest_non_null(db, room_id, "temp_out_c"),
            "humOut": _latest_non_null(db, room_id, "hum_out_pct"),
            "occupied": bool(pir_rows),
        },
        "history": history,
        "forecast": forecast,
        "recommendation": {
            "action": rec.action,
            "minutes": rec.minutes,
            "reason": reason_for(rec.action, rec.peak, rec.at15, s.th_high),
        },
        "events": _events(history, s),
    }


def _minus_minutes(ms: int, minutes: int) -> str:
    return ms_to_iso(ms - minutes * 60_000)
