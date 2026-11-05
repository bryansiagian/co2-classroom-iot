import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_windows import load_minutes, split_segments, generate_windows, export


class TestBuildWindows(unittest.TestCase):
    def make_csv(self, path, n=12, bad=()):
        start = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=[
                'minute_utc', 'co2_ppm', 'temp_in_c', 'hum_in_pct', 'pir', 'status'])
            w.writeheader()
            for i in range(n):
                w.writerow({'minute_utc': (start+timedelta(minutes=i)).isoformat().replace('+00:00','Z'),
                            'co2_ppm': 1000+i, 'temp_in_c':26, 'hum_in_pct':74,
                            'pir':i%2, 'status':'incomplete' if i in bad else 'usable'})

    def test_exact_horizon_and_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'all_minutes.csv'
            self.make_csv(path, 8)
            result = generate_windows(load_minutes(path), lookback=3, horizon=2)
            self.assertEqual(len(result), 4)  # n - lookback - horizon + 1
            self.assertEqual(len(result[0]['X']), 3)
            self.assertEqual(len(result[0]['X'][0]), 4)
            self.assertEqual(result[0]['input_end_utc'], '2026-11-04T14:02:00Z')
            self.assertEqual(result[0]['target_utc'], '2026-11-04T14:04:00Z')
            self.assertEqual(result[0]['y_co2_ppm'], 1004)

    def test_incomplete_minute_blocks_crossing_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'all_minutes.csv'
            self.make_csv(path, 12, bad=(5,))
            minutes = load_minutes(path)
            self.assertEqual([len(s) for s in split_segments(minutes)], [5, 6])
            result = generate_windows(minutes, lookback=3, horizon=2)
            self.assertEqual(len(result), 3)
            self.assertTrue(all(not (w['input_start_utc'] < '2026-11-04T14:05:00Z' < w['target_utc']) for w in result))

    def test_missing_timestamp_breaks_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'all_minutes.csv'
            self.make_csv(path, 9)
            with path.open() as f:
                rows = list(csv.DictReader(f))
            with path.open('w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader(); w.writerows(rows[:4]+rows[5:])
            self.assertEqual([len(s) for s in split_segments(load_minutes(path))], [4,4])
            self.assertEqual(generate_windows(load_minutes(path), 3, 2), [])

    def test_zero_windows_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            path = base/'all_minutes.csv'
            self.make_csv(path, 10)
            report = export(path, base/'out', 60, 15, 1)
            self.assertEqual(report['windows_created'], 0)
            self.assertTrue((base/'out/windows_index.csv').exists())
            self.assertEqual((base/'out/windows.jsonl').read_text(), '')

    def test_reject_duplicate_or_unsorted_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'all_minutes.csv'
            self.make_csv(path, 3)
            with path.open() as f: rows = list(csv.DictReader(f))
            rows[2]['minute_utc'] = rows[1]['minute_utc']
            with path.open('w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            with self.assertRaisesRegex(ValueError, 'timestamp unik'):
                load_minutes(path)

if __name__ == '__main__':
    unittest.main()
