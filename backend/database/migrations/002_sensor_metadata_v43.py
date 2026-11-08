
"""Add ESP32 V4.3 metadata columns without deleting existing readings."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


COLUMNS = {
    "boot_id": "TEXT",
    "uptime_ms": "INTEGER",
    "measured_at_utc": "TEXT",
}

INDEX_NAME = "idx_reading_device_boot_seq"


def migrate(db_path: Path) -> None:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database tidak ditemukan: {db_path}")

    db_path = db_path.resolve()

    # Buat backup konsisten menggunakan SQLite Backup API.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(
        f"{db_path.stem}.backup_{timestamp}{db_path.suffix}"
    )

    with sqlite3.connect(db_path, timeout=30) as source:
        with sqlite3.connect(backup_path) as backup:
            source.backup(backup)

    print(f"[BACKUP] {backup_path}")

    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")

        existing = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(sensor_reading)"
            )
        }

        if not existing:
            raise RuntimeError(
                "Tabel sensor_reading tidak ditemukan"
            )

        before = conn.execute(
            "SELECT COUNT(*) FROM sensor_reading"
        ).fetchone()[0]

        # Semua perubahan dijalankan dalam satu transaksi.
        conn.execute("BEGIN IMMEDIATE")

        try:
            for column, column_type in COLUMNS.items():
                if column not in existing:
                    conn.execute(
                        f"ALTER TABLE sensor_reading "
                        f"ADD COLUMN {column} {column_type}"
                    )
                    print(f"[ADD] {column} {column_type}")
                else:
                    print(f"[SKIP] {column} sudah ada")

            
            # Hapus indeks legacy lama yang berlaku untuk seluruh data.
            # Data sensor tidak dihapus.
            conn.execute("DROP INDEX IF EXISTS idx_reading_dedup")

            # Deduplikasi khusus payload V4.2 / legacy.
            conn.execute("""
                CREATE UNIQUE INDEX idx_reading_dedup
                ON sensor_reading (device_id, ts_utc, seq)
                WHERE boot_id IS NULL
            """)

            print("[INDEX] Legacy deduplication updated")

            # Deduplikasi payload V4.3 berdasarkan sesi boot.
            conn.execute(f"""
                CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
                ON sensor_reading (device_id, boot_id, seq)
                WHERE boot_id IS NOT NULL
                AND seq IS NOT NULL
            """)

            print("[INDEX] V4.3 deduplication ready")


            after = conn.execute(
                "SELECT COUNT(*) FROM sensor_reading"
            ).fetchone()[0]

            if before != after:
                raise RuntimeError(
                    f"Jumlah data berubah: {before} -> {after}"
                )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        integrity = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError(
                f"Integrity check gagal: {integrity}. "
                f"Backup tersedia di {backup_path}"
            )

        print("\n===== MIGRATION RESULT =====")
        print(f"Database     : {db_path}")
        print(f"Total sebelum: {before}")
        print(f"Total sesudah: {after}")
        print(f"Integrity    : {integrity}")
        print(f"Index        : {INDEX_NAME}")
        print("Status       : SUCCESS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "database",
        type=Path,
        help="Path database SQLite",
    )

    args = parser.parse_args()
    migrate(args.database)
