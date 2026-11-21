
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resample_sensor_data import resample, valid_row


class TestResample(unittest.TestCase):

    def test_valid_row_pir_must_be_integer_zero_or_one(self):
        columns = {
            "quality_flags": "[]",
            "faults": "[]",
            "pir": 0,
            "co2_ppm": 1000,
            "temp_in_c": 26.0,
            "hum_in_pct": 74.0,
        }

        self.assertTrue(valid_row(columns))

        columns["pir"] = 1
        self.assertTrue(valid_row(columns))

        columns["pir"] = True
        self.assertFalse(valid_row(columns))

        columns["pir"] = 1.0
        self.assertFalse(valid_row(columns))

        columns["pir"] = 2
        self.assertFalse(valid_row(columns))

    def test_complete_incomplete_missing_and_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE sensor_reading (id INTEGER PRIMARY KEY, room_id TEXT, received_at TEXT, co2_ppm INTEGER, temp_in_c REAL, hum_in_pct REAL, pir INTEGER, quality_flags TEXT, faults TEXT DEFAULT '[]')")

            def add(minute, seconds, co2=1000, flags='[]', pir=0, faults='[]'):
                con.execute(
                    "INSERT INTO sensor_reading(room_id, received_at, co2_ppm, temp_in_c, hum_in_pct, pir, quality_flags, faults) VALUES (?,?,?,?,?,?,?,?)",
                    ("gd525", f"2026-11-04T14:{minute:02}:{seconds:02}Z", co2, 26., 74., pir, flags, faults)
                )

            add(0, 40)
            for seconds in (0, 10, 20, 30, 40, 50):
                add(
                    1, seconds, 1200,
                    pir=1 if seconds == 30 else 0,
                    faults='["sensor_fault"]' if seconds == 0 else '[]'
                )

            for seconds in (0, 10, 20, 30):
                add(
                    2, seconds,
                    3000 if seconds == 10 else 1000,
                    flags='["suspect"]' if seconds == 10 else '[]'
                )

            add(4, 3)
            con.commit()
            con.close()

            all_minutes, usable, report = resample(db, "gd525", 6, 5)

            self.assertEqual(
                [r['status'] for r in all_minutes],
                ['boundary_partial', 'usable', 'incomplete', 'missing', 'boundary_partial']
            )
            self.assertEqual(len(usable), 1)
            self.assertEqual(usable[0]['co2_ppm'], 1200)
            self.assertEqual(usable[0]['pir'], 1)
            self.assertEqual(report['samples_rejected'], 2)
            self.assertEqual(report['minutes_missing'], 1)
            self.assertEqual(report['raw_rows'], 12)

    def test_valid_row_missing_column_returns_false(self):
        columns = {
            "quality_flags": "[]",
            "faults": "[]",
            "pir": 1,
            "co2_ppm": 1000,
            "temp_in_c": 26.0,
            # hum_in_pct sengaja dihilangkan
        }

        self.assertFalse(valid_row(columns))

    def test_empty_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'empty.db'
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE sensor_reading(id INTEGER, room_id TEXT, received_at TEXT, co2_ppm INTEGER, temp_in_c REAL, hum_in_pct REAL, pir INTEGER, quality_flags TEXT, faults TEXT DEFAULT '[]')")
            con.close()

            a, b, r = resample(db, 'gd525', 6, 5)
            self.assertEqual((a, b, r['minutes_total']), ([], [], 0))


if __name__ == '__main__':
    unittest.main()
