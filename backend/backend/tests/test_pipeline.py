import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.ingest import Pipeline
from app.main import create_app
from app.predictor import LinearDemoPredictor, PersistencePredictor
from app.recommend import recommend
from app.timeutil import to_iso
from tools.scenario import sensor_message

SCHEMA = os.path.join(os.path.dirname(__file__), "..", "..", "database", "schema.sql")
T0 = datetime(2026, 10, 19, 4, 0, tzinfo=timezone.utc)


@pytest.fixture
def settings():
    return Settings(mqtt_enabled=False, db_path=":memory:", schema_path=SCHEMA, predictor="linear")


@pytest.fixture
def db(settings):
    d = Database(":memory:", SCHEMA)
    yield d
    d.close()


def seed(pipeline, minutes=360, start=T0, **overrides):
    for i in range(minutes):
        t = start + timedelta(minutes=i)
        msg = sensor_message(int(t.timestamp() // 60), to_iso(t), seq=i)
        msg.update(overrides)
        pipeline.handle_sensor_message("gd525", msg, received_at=t)
    return start + timedelta(minutes=minutes - 1)


def test_ingest_and_dashboard_matches_contract(settings, db):
    pipe = Pipeline(db, settings, LinearDemoPredictor())
    seed(pipe)
    app = create_app(settings, db=db)
    with TestClient(app) as client:
        r = client.get("/api/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"room", "updatedAt", "current", "history", "forecast", "recommendation", "events"}
    assert set(d["current"]) == {"co2", "tempIn", "humIn", "tempOut", "humOut", "occupied"}
    assert len(d["history"]) == 360
    assert len(d["forecast"]) == 15
    assert d["forecast"][0]["t"] == d["history"][-1]["t"] + 60_000
    assert d["recommendation"]["action"] in {"none", "watch", "flush"}
    assert len(d["events"]) <= 5
    assert [p["t"] for p in d["history"]] == sorted(p["t"] for p in d["history"])


def test_no_data_returns_404(settings, db):
    with TestClient(create_app(settings, db=db)) as client:
        assert client.get("/api/dashboard").status_code == 404


def test_suspect_value_is_stored_but_flagged_and_excluded(settings, db):
    pipe = Pipeline(db, settings, PersistencePredictor())
    seed(pipe, minutes=10)
    t = T0 + timedelta(minutes=10)
    msg = sensor_message(0, to_iso(t), seq=10)
    msg["co2_ppm"] = 9999
    out = pipe.handle_sensor_message("gd525", msg, received_at=t)
    assert "suspect" in out["flags"]
    assert "recommendation" not in out
    assert db.query("SELECT COUNT(*) c FROM sensor_reading")[0]["c"] == 11
    assert len(pipe.recent_co2("gd525")) == 10  # yang suspect tidak ikut


def test_missing_or_far_timestamp_uses_receive_time(settings, db):
    pipe = Pipeline(db, settings, PersistencePredictor())
    t = T0
    msg = sensor_message(0, None, seq=0)  # tanpa ts
    out = pipe.handle_sensor_message("gd525", msg, received_at=t)
    assert "ts_corrected" in out["flags"] and out["ts"] == to_iso(t)
    msg2 = sensor_message(0, to_iso(t - timedelta(hours=2)), seq=1)  # ts terlalu jauh
    out2 = pipe.handle_sensor_message("gd525", msg2, received_at=t + timedelta(minutes=1))
    assert "ts_corrected" in out2["flags"]


def test_duplicate_message_is_ignored(settings, db):
    pipe = Pipeline(db, settings, PersistencePredictor())
    msg = sensor_message(0, to_iso(T0), seq=5)
    assert pipe.handle_sensor_message("gd525", msg, received_at=T0) is not None
    assert pipe.handle_sensor_message("gd525", msg, received_at=T0) is None
    assert db.query("SELECT COUNT(*) c FROM sensor_reading")[0]["c"] == 1


def test_bad_payloads_are_rejected_without_crash(settings, db):
    pipe = Pipeline(db, settings, PersistencePredictor())
    assert pipe.handle_sensor_message("gd525", b"bukan json") is None
    assert pipe.handle_sensor_message("gd525", json.dumps({"co2_ppm": 500})) is None  # tanpa device_id
    assert pipe.handle_sensor_message("gd525", json.dumps([1, 2])) is None


def test_null_co2_with_fault_is_stored_without_prediction(settings, db):
    pipe = Pipeline(db, settings, PersistencePredictor())
    msg = sensor_message(0, to_iso(T0), seq=0)
    msg.update(co2_ppm=None, faults=["co2"])
    out = pipe.handle_sensor_message("gd525", msg, received_at=T0)
    assert out is not None and "recommendation" not in out
    assert db.query("SELECT COUNT(*) c FROM prediction")[0]["c"] == 0


def test_recommendation_rules(settings):
    assert recommend([700.0] * 15, settings).action == "none"
    assert recommend([850.0] * 15, settings).action == "watch"
    r = recommend([900.0] * 14 + [1080.0], settings)
    assert (r.action, r.minutes) == ("flush", 3)
    assert recommend([1200.0] * 15, settings).minutes == 4
    assert recommend([1600.0] * 15, settings).minutes == 5


def test_recommendation_is_published_to_mqtt_callback(settings, db):
    sent = []
    pipe = Pipeline(db, settings, LinearDemoPredictor(), publisher=lambda room, p: sent.append((room, p)))
    seed(pipe, minutes=20)
    room, payload = sent[-1]
    assert room == "gd525"
    assert set(payload) == {"v", "ts", "action", "minutes", "predicted_peak_ppm", "predicted_at_15min_ppm", "model"}


def test_health_and_range_endpoints(settings, db):
    pipe = Pipeline(db, settings, PersistencePredictor())
    seed(pipe, minutes=30)
    with TestClient(create_app(settings, db=db)) as client:
        h = client.get("/api/health").json()
        assert h["stale"] is True  # data tahun 2026-10-19 04:00, jauh dari "sekarang"
        r = client.get("/api/readings", params={"from": "2026-10-19T04:00:00Z", "to": "2026-10-19T04:10:00Z"})
        assert r.status_code == 200 and len(r.json()) == 11
        bad = client.get("/api/readings", params={"from": "kemarin", "to": "hari ini"})
        assert bad.status_code == 422
