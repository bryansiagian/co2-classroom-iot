"""Uji format payload asli ESP32 V3 tanpa broker/H200."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.db import Database
from app.ingest import Pipeline
from app.mqtt_client import MqttBridge
from app.predictor import PersistencePredictor

SCHEMA = Path(__file__).resolve().parents[2] / "database" / "schema.sql"


def test_esp32_v3_payload_is_saved():
    settings = Settings(mqtt_enabled=False, mqtt_tls_enabled=False)
    db = Database(":memory:", str(SCHEMA))
    try:
        pipeline = Pipeline(db, settings, PersistencePredictor())
        received = datetime(2026, 11, 3, 14, 39, 59, tzinfo=timezone.utc)
        payload = {"co2": 943, "temperature": 24.4, "humidity": 83.6, "pir": 1}
        result = pipeline.handle_sensor_message("gd525", payload, received_at=received)
        assert result is not None
        rows = db.query("SELECT device_id, co2_ppm, temp_in_c, hum_in_pct, pir, quality_flags FROM sensor_reading")
        assert len(rows) == 1
        assert tuple(rows[0])[:5] == ("esp32_gd525", 943, 24.4, 83.6, 1)
        assert "ts_corrected" in json.loads(rows[0]["quality_flags"])
    finally:
        db.close()


def test_mqtt_topic_esp32_v3():
    settings = Settings(mqtt_enabled=False, mqtt_tls_enabled=False)
    db = Database(":memory:", str(SCHEMA))
    try:
        pipeline = Pipeline(db, settings, PersistencePredictor())
        bridge = MqttBridge(settings, pipeline)
        msg = SimpleNamespace(topic="classroom/gd525/sensors", payload=b'{"co2":943,"temperature":24.4,"humidity":83.6,"pir":1}')
        bridge._on_message(None, None, msg)
        assert db.query("SELECT COUNT(*) AS n FROM sensor_reading")[0]["n"] == 1
    finally:
        db.close()
