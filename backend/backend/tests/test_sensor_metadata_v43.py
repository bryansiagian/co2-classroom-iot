
"""Unit tests for ESP32 V4.3 sensor metadata and deduplication."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.ingest import Pipeline
from app.predictor import PersistencePredictor
from app.timeutil import to_iso


SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "database"
    / "schema.sql"
)

T0 = datetime(2026, 11, 8, 3, 0, 0, tzinfo=timezone.utc)


def make_pipeline():
    settings = Settings(
        mqtt_enabled=False,
        db_path=":memory:",
        schema_path=str(SCHEMA),
    )

    db = Database(":memory:", str(SCHEMA))
    pipeline = Pipeline(db, settings, PersistencePredictor())

    return db, pipeline


def sensor_message(
    boot_id="boot-A",
    seq=1,
    uptime_ms=120000,
    measured_at_utc=None,
):
    return {
        "device_id": "esp32_gd525",
        "boot_id": boot_id,
        "seq": seq,
        "uptime_ms": uptime_ms,
        "measured_at_utc": measured_at_utc,
        "ts": None,
        "co2_ppm": 850,
        "temp_in_c": 27.2,
        "hum_in_pct": 75.4,
        "pir": 1,
        "faults": [],
    }


def count_readings(db):
    return db.query(
        "SELECT COUNT(*) AS total FROM sensor_reading"
    )[0]["total"]


def test_v43_metadata_is_saved():
    db, pipeline = make_pipeline()

    msg = sensor_message(
        boot_id="boot-A",
        seq=42,
        uptime_ms=420000,
    )

    result = pipeline.handle_sensor_message(
        "gd525",
        msg,
        received_at=T0,
    )

    assert result is not None

    row = db.query(
        """
        SELECT device_id, boot_id, seq, uptime_ms,
               received_at, measured_at_utc, raw
        FROM sensor_reading
        """
    )[0]

    assert row["device_id"] == "esp32_gd525"
    assert row["boot_id"] == "boot-A"
    assert row["seq"] == 42
    assert row["uptime_ms"] == 420000
    assert row["received_at"] == to_iso(T0)
    assert row["measured_at_utc"] is None

    raw = json.loads(row["raw"])
    assert raw["boot_id"] == "boot-A"
    assert raw["seq"] == 42


def test_duplicate_with_same_boot_and_seq_is_rejected():
    db, pipeline = make_pipeline()

    msg = sensor_message(
        boot_id="boot-A",
        seq=10,
    )

    first = pipeline.handle_sensor_message(
        "gd525",
        msg,
        received_at=T0,
    )

    second = pipeline.handle_sensor_message(
        "gd525",
        msg,
        received_at=T0 + timedelta(seconds=30),
    )

    assert first is not None
    assert second is None
    assert count_readings(db) == 1


def test_same_sequence_from_different_boot_is_accepted():
    db, pipeline = make_pipeline()

    first_msg = sensor_message(
        boot_id="boot-A",
        seq=1,
    )

    second_msg = sensor_message(
        boot_id="boot-B",
        seq=1,
    )

    first = pipeline.handle_sensor_message(
        "gd525",
        first_msg,
        received_at=T0,
    )

    second = pipeline.handle_sensor_message(
        "gd525",
        second_msg,
        received_at=T0 + timedelta(seconds=10),
    )

    assert first is not None
    assert second is not None
    assert count_readings(db) == 2


def test_valid_measurement_timestamp_is_preserved():
    db, pipeline = make_pipeline()

    measured = T0 - timedelta(seconds=5)

    msg = sensor_message(
        measured_at_utc=to_iso(measured),
    )

    result = pipeline.handle_sensor_message(
        "gd525",
        msg,
        received_at=T0,
    )

    assert result is not None

    row = db.query(
        """
        SELECT ts_utc, received_at,
               measured_at_utc, quality_flags
        FROM sensor_reading
        """
    )[0]

    assert row["measured_at_utc"] == to_iso(measured)
    assert row["received_at"] == to_iso(T0)
    assert row["ts_utc"] == to_iso(measured)
    assert "ts_corrected" not in json.loads(
        row["quality_flags"]
    )


def test_delayed_measurement_keeps_original_timestamp():
    db, pipeline = make_pipeline()

    measured = T0 - timedelta(hours=2)

    msg = sensor_message(
        measured_at_utc=to_iso(measured),
    )

    result = pipeline.handle_sensor_message(
        "gd525",
        msg,
        received_at=T0,
    )

    assert result is not None

    row = db.query(
        """
        SELECT ts_utc, received_at,
               measured_at_utc, quality_flags
        FROM sensor_reading
        """
    )[0]

    # Metadata asli tetap disimpan.
    assert row["measured_at_utc"] == to_iso(measured)

    # Timestamp efektif dikoreksi sesuai kontrak saat ini.
    assert row["ts_utc"] == to_iso(T0)
    assert row["received_at"] == to_iso(T0)

    flags = json.loads(row["quality_flags"])
    assert "ts_corrected" in flags


def test_missing_sequence_is_flagged():
    db, pipeline = make_pipeline()

    msg = sensor_message(
        boot_id="boot-A",
        seq=None,
    )

    result = pipeline.handle_sensor_message(
        "gd525",
        msg,
        received_at=T0,
    )

    assert result is not None

    row = db.query(
        "SELECT seq, quality_flags FROM sensor_reading"
    )[0]

    assert row["seq"] is None

    flags = json.loads(row["quality_flags"])
    assert "sequence_missing" in flags


def test_legacy_payload_remains_supported():
    db, pipeline = make_pipeline()

    legacy_msg = {
        "co2": 900,
        "temperature": 27.0,
        "humidity": 75.0,
        "pir": 1,
    }

    result = pipeline.handle_sensor_message(
        "gd525",
        legacy_msg,
        received_at=T0,
    )

    assert result is not None
    assert count_readings(db) == 1

    row = db.query(
        """
        SELECT device_id, boot_id, uptime_ms, co2_ppm
        FROM sensor_reading
        """
    )[0]

    assert row["device_id"] == "esp32_gd525"
    assert row["boot_id"] is None
    assert row["uptime_ms"] is None
    assert row["co2_ppm"] == 900
