import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resample_sensor_data import resample


class TestResample(unittest.TestCase):
    def test_complete_incomplete_missing_and_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE sensor_reading (id INTEGER PRIMARY KEY, room_id TEXT, received_at TEXT, co2_ppm INTEGER, temp_in_c REAL, hum_in_pct REAL, pir INTEGER, quality_flags TEXT)")
            def add(minute, seconds, co2=1000, flags='[]', pir=0):
                con.execute("INSERT INTO sensor_reading(room_id, received_at, co2_ppm, temp_in_c, hum_in_pct, pir, quality_flags) VALUES (?,?,?,?,?,?,?)",
                            ("gd525", f"2026-11-04T14:{minute:02}:{seconds:02}Z", co2, 26., 74., pir, flags))
            add(0, 40)
            for seconds in (0, 10, 20, 30, 40, 50):
                add(1, seconds, 1200, pir=1 if seconds == 30 else 0)
            for seconds in (0, 10, 20, 30):
                add(2, seconds, 3000 if seconds == 10 else 1000, flags='["suspect"]' if seconds == 10 else '[]')
            add(4, 3)
            con.commit()
            con.close()
            all_minutes, usable, report = resample(db, "gd525", 6, 5)
            self.assertEqual([r['status'] for r in all_minutes], ['boundary_partial', 'usable', 'incomplete', 'missing', 'boundary_partial'])
            self.assertEqual(len(usable), 1)
            self.assertEqual(usable[0]['co2_ppm'], 1200)
            self.assertEqual(usable[0]['pir'], 1)
            self.assertEqual(report['samples_rejected'], 1)
            self.assertEqual(report['minutes_missing'], 1)
            self.assertEqual(report['raw_rows'], 12)

    def test_empty_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'empty.db'
            con = sqlite3.connect(db)
            con.execute('CREATE TABLE sensor_reading(id INTEGER, room_id TEXT, received_at TEXT, co2_ppm INTEGER, temp_in_c REAL, hum_in_pct REAL, pir INTEGER, quality_flags TEXT)')
            con.close()
            a, b, r = resample(db, 'gd525', 6, 5)
            self.assertEqual((a, b, r['minutes_total']), ([], [], 0))


if __name__ == '__main__':
    unittest.main()
