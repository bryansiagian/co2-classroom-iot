
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

    def test_device_filter_does_not_mix_sensors(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "devices.db"
            con = sqlite3.connect(db)
            con.execute("""
                CREATE TABLE sensor_reading (
                    id INTEGER PRIMARY KEY, room_id TEXT, device_id TEXT,
                    received_at TEXT, co2_ppm INTEGER, temp_in_c REAL,
                    hum_in_pct REAL, pir INTEGER, quality_flags TEXT, faults TEXT
                )
            """)
            for seconds in (0, 10, 20, 30, 40, 50):
                for device, co2 in (("esp32_gd525", 500), ("esp32_gd525_02", 1500)):
                    con.execute("""
                        INSERT INTO sensor_reading (
                            room_id, device_id, received_at, co2_ppm,
                            temp_in_c, hum_in_pct, pir, quality_flags, faults
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, ("gd525", device, f"2026-11-09T11:01:{seconds:02}Z",
                          co2, 26.0, 74.0, 0, "[]", "[]"))
            # Menit pertama dan terakhir sengaja disediakan sebagai boundary.
            for minute in (0, 2):
                for device in ("esp32_gd525", "esp32_gd525_02"):
                    con.execute("""
                        INSERT INTO sensor_reading (
                            room_id, device_id, received_at, co2_ppm,
                            temp_in_c, hum_in_pct, pir, quality_flags, faults
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, ("gd525", device, f"2026-11-09T11:{minute:02}:00Z",
                          600, 26.0, 74.0, 0, "[]", "[]"))
            con.commit()
            con.close()

            _, usable_one, report_one = resample(db, "gd525", 6, 5, device_id="esp32_gd525")
            _, usable_two, report_two = resample(db, "gd525", 6, 5, device_id="esp32_gd525_02")
            self.assertEqual(len(usable_one), 1)
            self.assertEqual(len(usable_two), 1)
            self.assertEqual(usable_one[0]["co2_ppm"], 500)
            self.assertEqual(usable_two[0]["co2_ppm"], 1500)
            self.assertEqual(report_one["raw_rows"], 8)
            self.assertEqual(report_two["raw_rows"], 8)
            self.assertEqual(report_one["device_id"], "esp32_gd525")
            self.assertEqual(report_two["device_id"], "esp32_gd525_02")

    def test_dht_fault_retains_co2_only_and_rejects_multivariate(self):
        from resample_sensor_data import valid_co2_row
        row = {
            "quality_flags": "[]", "faults": '["temperature", "humidity"]',
            "co2_ppm": 817, "temp_in_c": None, "hum_in_pct": None, "pir": 1,
        }
        self.assertTrue(valid_co2_row(row))
        self.assertFalse(valid_row(row))
        row["faults"] = '["co2"]'
        self.assertFalse(valid_co2_row(row))
        row["faults"] = '["temperature"]'
        row["quality_flags"] = '["suspect"]'
        self.assertFalse(valid_co2_row(row))
        row["quality_flags"] = "[]"
        row["co2_ppm"] = None
        self.assertFalse(valid_co2_row(row))

    def test_profiles_keep_separate_usable_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "profiles.db"
            con = sqlite3.connect(db)
            con.execute("""
                CREATE TABLE sensor_reading (
                    id INTEGER PRIMARY KEY, room_id TEXT, device_id TEXT,
                    received_at TEXT, co2_ppm INTEGER, temp_in_c REAL,
                    hum_in_pct REAL, pir INTEGER, quality_flags TEXT, faults TEXT
                )
            """)
            for minute in range(3):
                seconds = (0, 10, 20, 30, 40, 50) if minute == 1 else (0,)
                for second in seconds:
                    dht_fault = minute == 1 and second in (0, 10)
                    con.execute("""
                        INSERT INTO sensor_reading (
                            room_id, device_id, received_at, co2_ppm,
                            temp_in_c, hum_in_pct, pir, quality_flags, faults
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, ("gd525", "esp32_gd525",
                          f"2026-11-09T11:{minute:02}:{second:02}Z", 817,
                          None if dht_fault else 26.0,
                          None if dht_fault else 74.0, 0, "[]",
                          '["temperature", "humidity"]' if dht_fault else "[]"))
            con.commit()
            con.close()

            a_multi, usable_multi, report_multi = resample(
                db, "gd525", 6, 5, device_id="esp32_gd525",
                profile="multivariate"
            )
            a_co2, usable_co2, report_co2 = resample(
                db, "gd525", 6, 5, device_id="esp32_gd525",
                profile="co2_only"
            )
            self.assertEqual(a_multi[1]["status"], "incomplete")
            self.assertEqual(a_co2[1]["status"], "usable")
            self.assertEqual(len(usable_multi), 0)
            self.assertEqual(len(usable_co2), 1)
            self.assertEqual(usable_co2[0]["co2_ppm"], 817)
            self.assertEqual(usable_co2[0]["temp_in_c"], "")
            self.assertEqual(usable_co2[0]["hum_in_pct"], "")
            self.assertEqual(usable_co2[0]["pir"], "")
            self.assertEqual(report_multi["samples_rejected"], 2)
            self.assertEqual(report_co2["samples_rejected"], 0)
            self.assertEqual(report_multi["profile"], "multivariate")
            self.assertEqual(report_co2["profile"], "co2_only")

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
