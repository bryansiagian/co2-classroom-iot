"""Menguji logika MqttBridge tanpa broker sungguhan (callback dipanggil langsung)."""
import json
import os
from types import SimpleNamespace

from app.config import Settings
from app.db import Database
from app.ingest import Pipeline
from app.mqtt_client import MqttBridge
from app.predictor import PersistencePredictor
from app.timeutil import to_iso, utcnow
from tools.scenario import sensor_message

SCHEMA = os.path.join(os.path.dirname(__file__), "..", "..", "database", "schema.sql")


def make():
    s = Settings(mqtt_enabled=False, db_path=":memory:", schema_path=SCHEMA)
    db = Database(":memory:", SCHEMA)
    pipe = Pipeline(db, s, PersistencePredictor())
    bridge = MqttBridge(s, pipe)
    published = []
    bridge._client.publish = lambda topic, payload, qos=0, retain=False: published.append((topic, json.loads(payload), qos, retain))
    pipe.publisher = bridge.publish_recommendation
    return db, bridge, published


def test_sensor_message_is_stored_and_recommendation_published():
    db, bridge, published = make()
    now = utcnow()
    payload = json.dumps(sensor_message(int(now.timestamp() // 60), to_iso(now), seq=0)).encode()
    bridge._on_message(None, None, SimpleNamespace(topic="co2class/gd525/sensor", payload=payload))
    assert db.query("SELECT COUNT(*) c FROM sensor_reading")[0]["c"] == 1
    topic, body, qos, retain = published[-1]
    assert topic == "co2class/gd525/recommendation" and qos == 1 and retain is True
    assert body["action"] in {"none", "watch", "flush"}


def test_status_message_and_garbage_do_not_crash():
    db, bridge, _ = make()
    bridge._on_message(None, None, SimpleNamespace(topic="co2class/gd525/status", payload=b"online"))
    assert bridge.device_status["gd525"] == "online"
    bridge._on_message(None, None, SimpleNamespace(topic="co2class/gd525/sensor", payload=b"\xff\xfe"))
    bridge._on_message(None, None, SimpleNamespace(topic="salah/topik", payload=b"{}"))
    assert db.query("SELECT COUNT(*) c FROM sensor_reading")[0]["c"] == 0
