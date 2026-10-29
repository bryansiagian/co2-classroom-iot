"""Konfigurasi dari environment variable (opsional lewat file .env)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

# .env di root repo dipakai bersama; .env di backend/ boleh menimpa.
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env", override=True)


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    room_id: str = os.getenv("ROOM_ID", "gd525")
    room_label: str = os.getenv("ROOM_LABEL", "GD 525")

    mqtt_enabled: bool = _bool("MQTT_ENABLED", True)
    mqtt_host: str = os.getenv("MQTT_HOST", "localhost")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_username: str = os.getenv("MQTT_USERNAME", "")
    mqtt_password: str = os.getenv("MQTT_PASSWORD", "")
    mqtt_topic_prefix: str = os.getenv("MQTT_TOPIC_PREFIX", "co2class")

    db_path: str = os.getenv("DB_PATH", str(BACKEND_DIR / "data" / "co2class.db"))
    schema_path: str = os.getenv("DB_SCHEMA_PATH", str(REPO_ROOT / "database" / "schema.sql"))

    # persistence (sesuai docs), linear (demo), gru (setelah model dari ml/ tersedia)
    predictor: str = os.getenv("PREDICTOR", "persistence")
    model_path: str = os.getenv("MODEL_PATH", "")

    th_watch: float = float(os.getenv("TH_WATCH", "800"))
    th_high: float = float(os.getenv("TH_HIGH", "1000"))
    th_critical: float = float(os.getenv("TH_CRITICAL", "1500"))

    ts_tolerance_s: int = int(os.getenv("TS_TOLERANCE_S", "300"))
    stale_after_s: int = int(os.getenv("STALE_AFTER_S", "180"))

    cors_origins: tuple[str, ...] = tuple(
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if o.strip()
    )


settings = Settings()
