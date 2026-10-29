"""Aplikasi FastAPI: REST API untuk dashboard dan penerima MQTT."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, settings as default_settings
from .dashboard import build_dashboard
from .db import Database
from .ingest import Pipeline
from .mqtt_client import MqttBridge
from .predictor import build_predictor
from .timeutil import iso_to_ms, parse_iso, utcnow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings = default_settings, db: Database | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = db or Database(settings.db_path, settings.schema_path)
        predictor = build_predictor(settings.predictor, settings.model_path)
        pipeline = Pipeline(database, settings, predictor)
        bridge = None
        if settings.mqtt_enabled:
            bridge = MqttBridge(settings, pipeline)
            pipeline.publisher = bridge.publish_recommendation
            bridge.start()
        app.state.db, app.state.predictor, app.state.pipeline, app.state.bridge = database, predictor, pipeline, bridge
        yield
        if bridge:
            bridge.stop()
        if db is None:
            database.close()

    app = FastAPI(title="CO2 Classroom IoT API", version="1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET"], allow_headers=["*"])

    @app.get("/api/dashboard")
    def dashboard():
        data = build_dashboard(app.state.db, settings, app.state.predictor, settings.room_id)
        if data is None:
            raise HTTPException(404, "Belum ada data sensor yang valid untuk ruang ini")
        return data

    @app.get("/api/health")
    def health():
        rows = app.state.db.query(
            "SELECT ts_utc FROM sensor_reading WHERE room_id=? ORDER BY ts_utc DESC LIMIT 1", (settings.room_id,))
        last_at = rows[0]["ts_utc"] if rows else None
        age = int((utcnow() - parse_iso(last_at)).total_seconds()) if last_at else None
        bridge: MqttBridge | None = app.state.bridge
        return {
            "status": "ok",
            "mqtt": {"enabled": settings.mqtt_enabled, "connected": bool(bridge and bridge.connected)},
            "device_status": dict(bridge.device_status) if bridge else {},
            "predictor": app.state.predictor.name,
            "last_reading_at": last_at,
            "last_reading_age_s": age,
            "stale": age is None or age > settings.stale_after_s,
        }

    @app.get("/api/readings")
    def readings(from_: str = Query(alias="from"), to: str = Query(), limit: int = Query(5000, le=20000)):
        _validate_range(from_, to)
        rows = app.state.db.query(
            """SELECT ts_utc, device_id, co2_ppm, temp_in_c, hum_in_pct, temp_out_c, hum_out_pct, pir,
                      faults, quality_flags
               FROM sensor_reading WHERE room_id=? AND ts_utc>=? AND ts_utc<=? ORDER BY ts_utc LIMIT ?""",
            (settings.room_id, from_, to, limit))
        return [dict(r) for r in rows]

    @app.get("/api/predictions")
    def predictions(from_: str = Query(alias="from"), to: str = Query(), limit: int = Query(5000, le=20000)):
        _validate_range(from_, to)
        rows = app.state.db.query(
            """SELECT created_at, target_ts, horizon_min, co2_ppm, model FROM prediction
               WHERE room_id=? AND created_at>=? AND created_at<=? ORDER BY created_at, horizon_min LIMIT ?""",
            (settings.room_id, from_, to, limit))
        return [dict(r) for r in rows]

    return app


def _validate_range(a: str, b: str) -> None:
    try:
        iso_to_ms(a), iso_to_ms(b)
    except ValueError:
        raise HTTPException(422, "Format waktu harus ISO 8601 UTC, contoh 2026-10-19T04:30:00Z")


app = create_app()
