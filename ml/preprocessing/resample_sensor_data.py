#!/usr/bin/env python3
"""Audit-safe, read-only SQLite -> UTC 1-minute CSV export for GD525 development data.

Does not interpolate or modify sensor_reading. Uses backend receipt time because
ESP32 V4.1 does not include an independently verified measurement timestamp.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "backend/backend/data/co2class.db"
DEFAULT_OUT = REPO_ROOT / "ml/data/processed/development"
HEADERS = ["minute_utc", "co2_ppm", "temp_in_c", "hum_in_pct", "pir", "n_received", "n_valid", "n_rejected", "coverage_pct", "status"]
RANGES = {"co2_ppm": (350, 5000), "temp_in_c": (-10, 60), "hum_in_pct": (0, 100)}


def parse_timestamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp tanpa timezone")
    return dt.astimezone(timezone.utc)


def valid_row(row: sqlite3.Row) -> bool:
    try:
        flags = json.loads(row["quality_flags"] or "[]")
        if not isinstance(flags, list) or any(str(f).lower() == "suspect" or str(f).lower().endswith("_suspect") for f in flags):
            return False
        if row["pir"] not in (0, 1):
            return False
        for col, (lo, hi) in RANGES.items():
            x = row[col]
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)) or not lo <= x <= hi:
                return False
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return True


def resample(db_path: Path, room: str, expected: int, min_samples: int):
    if not db_path.is_file():
        raise FileNotFoundError(f"Database tidak ditemukan: {db_path}")
    db_uri = db_path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(db_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("""
            SELECT received_at, co2_ppm, temp_in_c, hum_in_pct, pir, quality_flags
            FROM sensor_reading WHERE room_id=? ORDER BY received_at, id
        """, (room,)).fetchall()
    finally:
        connection.close()

    minutes = defaultdict(list)
    invalid_timestamps = 0
    parsed_times = []
    for row in rows:
        try:
            ts = parse_timestamp(row["received_at"])
        except (ValueError, TypeError, AttributeError):
            invalid_timestamps += 1
            continue
        minute = ts.replace(second=0, microsecond=0)
        minutes[minute].append(row)
        parsed_times.append(ts)

    if not parsed_times:
        return [], [], {"room_id": room, "raw_rows": len(rows), "invalid_timestamps": invalid_timestamps, "minutes_total": 0, "minutes_usable": 0, "minutes_incomplete": 0, "minutes_missing": 0, "minutes_boundary": 0, "samples_rejected": 0}

    first_minute = min(parsed_times).replace(second=0, microsecond=0)
    last_minute = max(parsed_times).replace(second=0, microsecond=0)
    cursor = first_minute
    output = []
    rejected = 0
    while cursor <= last_minute:
        source = minutes.get(cursor, [])
        valid = [row for row in source if valid_row(row)]
        rejected += len(source) - len(valid)
        is_boundary = cursor in (first_minute, last_minute)
        if not source:
            status = "missing"
        elif is_boundary:
            status = "boundary_partial"
        elif len(valid) < min_samples:
            status = "incomplete"
        else:
            status = "usable"
        n = len(valid)
        output.append({
            "minute_utc": cursor.isoformat().replace("+00:00", "Z"),
            "co2_ppm": round(sum(r["co2_ppm"] for r in valid) / n, 3) if n else "",
            "temp_in_c": round(sum(r["temp_in_c"] for r in valid) / n, 3) if n else "",
            "hum_in_pct": round(sum(r["hum_in_pct"] for r in valid) / n, 3) if n else "",
            "pir": max(r["pir"] for r in valid) if n else "",
            "n_received": len(source), "n_valid": n,
            "n_rejected": len(source) - n,
            "coverage_pct": round(min(100, 100 * n / expected), 1),
            "status": status,
        })
        cursor += timedelta(minutes=1)

    usable = [r for r in output if r["status"] == "usable"]
    report = {
        "room_id": room, "source_database": str(db_path), "timestamp_source": "received_at (UTC)",
        "expected_samples_per_minute": expected, "minimum_valid_samples": min_samples,
        "raw_rows": len(rows), "invalid_timestamps": invalid_timestamps,
        "samples_rejected": rejected, "minutes_total": len(output),
        "minutes_usable": len(usable),
        "minutes_incomplete": sum(r["status"] == "incomplete" for r in output),
        "minutes_missing": sum(r["status"] == "missing" for r in output),
        "minutes_boundary": sum(r["status"] == "boundary_partial" for r in output),
        "first_minute_utc": output[0]["minute_utc"], "last_minute_utc": output[-1]["minute_utc"],
        "warnings": ["Data development; jangan diklaim sebagai pengukuran resmi GD525.",
                     "Tidak ada interpolasi; putuskan segmen kontinu sebelum membuat window GRU.",
                     "received_at bukan waktu pengukuran ESP32; ts_corrected diperbolehkan."],
    }
    return output, usable, report


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ekspor SQLite sensor GD525 ke grid UTC 1 menit (read-only)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--room", default="gd525")
    parser.add_argument("--expected", type=int, default=6, help="Jumlah sampel ideal per menit pada interval 10 detik")
    parser.add_argument("--min-samples", type=int, default=5, help="Minimum sampel valid untuk usable")
    args = parser.parse_args()
    if not 1 <= args.min_samples <= args.expected:
        parser.error("--min-samples harus >=1 dan <= --expected")
    if args.db.resolve() == (args.out_dir / "all_minutes.csv").resolve():
        parser.error("Direktori output tidak boleh menimpa database")
    all_rows, usable, report = resample(args.db, args.room, args.expected, args.min_samples)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "all_minutes.csv", all_rows)
    write_csv(args.out_dir / "usable_minutes.csv", usable)
    (args.out_dir / "resample_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Output: {args.out_dir.resolve()}")


if __name__ == "__main__":
    main()
