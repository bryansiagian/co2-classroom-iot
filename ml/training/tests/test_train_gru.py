import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from train_gru import FEATURES, StandardScaler, evaluate, make_windows, split_by_usable_time, split_by_fixed_boundaries


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

    def test_shared_time_boundaries_for_profiles(self):
        multi = minutes(600)
        co2 = [{"ts": row["ts"], "usable": row["usable"],
                "values": (row["values"][0],)} for row in multi]
        # CO2-only retains readings unavailable to multivariate.
        for i in (150, 151, 152, 500):
            multi[i]["usable"] = False
        _, boundaries = split_by_usable_time(multi)
        train_end = datetime.fromisoformat(boundaries["train_end_utc"])
        val_end = datetime.fromisoformat(boundaries["val_end_utc"])
        multi_parts = split_by_fixed_boundaries(multi, train_end, val_end)
        co2_parts = split_by_fixed_boundaries(co2, train_end, val_end)
        self.assertEqual(
            [r["ts"] for r in multi_parts["test"]],
            [r["ts"] for r in co2_parts["test"]],
        )
        multi_test = make_windows(multi_parts["test"], 15, 15)
        co2_test = make_windows(co2_parts["test"], 15, 15)
        eligible = {window[3] for window in multi_test}
        aligned = [window for window in co2_test if window[3] in eligible]
        self.assertEqual([w[3] for w in aligned], [w[3] for w in multi_test])

    def test_univariate_training_scaler(self):
        rows = minutes(100)
        co2 = [{**r, "values": (r["values"][0],)} for r in rows]
        parts, _ = split_by_usable_time(co2)
        scaler = StandardScaler.fit(parts["train"], feature_names=("co2_ppm",))
        self.assertEqual(scaler.as_dict()["features"], ["co2_ppm"])
        self.assertEqual(len(scaler.transform((400.0,))), 1)
        with self.assertRaisesRegex(ValueError, "feature count"):
            scaler.transform((400.0, 26.0))

    def test_persistence_metrics(self):
        self.assertEqual(evaluate([100., 105.], [100., 100.])["MAE_ppm"], 2.5)

if __name__ == "__main__":
    unittest.main()
