"""Mengisi database dengan riwayat simulasi supaya dashboard langsung terlihat hidup.

Jalankan dari folder backend/:
    python -m tools.seed_db --hours 6 --reset
Data ini simulasi, jangan dipakai sebagai data TA.
"""
import argparse
import os
from datetime import timedelta

from app.config import settings
from app.db import Database
from app.ingest import Pipeline
from app.predictor import build_predictor
from app.timeutil import to_iso, utcnow

from .scenario import sensor_message


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=6)
    ap.add_argument("--reset", action="store_true", help="hapus database lama dulu")
    args = ap.parse_args()

    if args.reset and settings.db_path != ":memory:" and os.path.exists(settings.db_path):
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(settings.db_path + suffix):
                os.remove(settings.db_path + suffix)

    db = Database(settings.db_path, settings.schema_path)
    pipeline = Pipeline(db, settings, build_predictor(settings.predictor, settings.model_path))
    now = utcnow().replace(second=0)
    n = int(args.hours * 60)
    for i in range(n, -1, -1):
        t = now - timedelta(minutes=i)
        minute = int(t.timestamp() // 60)
        pipeline.handle_sensor_message(settings.room_id, sensor_message(minute, to_iso(t), seq=n - i), received_at=t)
    print(f"Selesai: {n + 1} pembacaan simulasi dimasukkan ke {settings.db_path}")


if __name__ == "__main__":
    main()
