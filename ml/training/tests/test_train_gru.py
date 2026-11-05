import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from train_gru import FEATURES, StandardScaler, evaluate, make_windows, split_by_usable_time


def minutes(n=600):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [{"ts": start + timedelta(minutes=i), "usable": True,
             "values": (float(i+400), 25.0, 60.0, float(i % 2))} for i in range(n)]

class TestTrainingData(unittest.TestCase):
    def test_split_precedes_windowing_and_no_overlap(self):
        parts, bounds = split_by_usable_time(minutes(600))
        windows = {k: make_windows(v, 15, 15) for k,v in parts.items()}
        self.assertEqual({k: len(v) for k,v in windows.items()}, {"train":391,"val":61,"test":61})
        self.assertLess(windows["train"][-1][3], windows["val"][0][2])
        self.assertLess(windows["val"][-1][3], windows["test"][0][2])

    def test_gaps_block_windows(self):
        rows = minutes(100)
        rows[25]["usable"] = False
        self.assertTrue(all(not (w[2] < rows[25]["ts"] < w[3]) for w in make_windows(rows, 15, 15)))
        self.assertEqual(len(make_windows(rows, 15, 15)), 45)

    def test_train_only_scaler(self):
        parts, _ = split_by_usable_time(minutes(100))
        scaler = StandardScaler.fit(parts["train"])
        self.assertAlmostEqual(scaler.means[0], 434.5)
        self.assertNotAlmostEqual(scaler.means[0], 449.5)
        self.assertAlmostEqual(scaler.transform(parts["train"][0]["values"])[0], (400-434.5)/scaler.stds[0])

    def test_persistence_metrics(self):
        self.assertEqual(evaluate([100., 105.], [100., 100.])["MAE_ppm"], 2.5)

if __name__ == "__main__":
    unittest.main()
