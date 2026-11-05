"""Chronological, leakage-conscious training for GD525 1-minute CO2 forecasting.

Input: ml/data/processed/development/all_minutes.csv (resample_sensor_data.py)
Split raw usable minute timestamps chronologically BEFORE creating windows.
Each lookback AND target must remain fully inside its own split and continuous.
Scaler fits ONLY on training minutes. No synthetic data or interpolation.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

FEATURES = ("co2_ppm", "temp_in_c", "hum_in_pct", "pir")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "ml/data/processed/development/all_minutes.csv"
DEFAULT_OUTPUT = ROOT / "ml/data/processed/development/gru_training"


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp must contain UTC offset")
    return dt.astimezone(timezone.utc)


def load_minutes(path: Path) -> list[dict]:
    result = []
    with path.open(newline="", encoding="utf-8") as fp:
        for raw in csv.DictReader(fp):
            minute = parse_utc(raw["minute_utc"])
            usable = raw["status"] == "usable"
            vals = None
            if usable:
                try:
                    vals = tuple(float(raw[f]) for f in FEATURES)
                    if not all(math.isfinite(x) for x in vals):
                        usable = False
                except (ValueError, TypeError):
                    usable = False
            result.append({"ts": minute, "usable": usable, "values": vals if usable else None})
    if not result:
        raise ValueError("CSV is empty")
    if any(a["ts"] >= b["ts"] for a, b in zip(result, result[1:])):
        raise ValueError("Timestamps must be strictly increasing and unique")
    return result


def split_by_usable_time(rows: list[dict], train_ratio=0.70, val_ratio=0.15):
    """Chronological boundaries based on timestamps of valid, usable minutes.

    Never reorders rows. Segment membership is based solely on timestamp.
    """
    usable = [r["ts"] for r in rows if r["usable"]]
    if len(usable) < 3:
        raise ValueError("At least three usable minutes required")
    train_n = max(1, int(len(usable) * train_ratio))
    val_n = max(1, int(len(usable) * val_ratio))
    if train_n + val_n >= len(usable):
        raise ValueError("Too few usable minutes for three chronological splits")
    train_end = usable[train_n - 1]
    val_end = usable[train_n + val_n - 1]
    parts = {"train": [], "val": [], "test": []}
    for row in rows:
        part = "train" if row["ts"] <= train_end else "val" if row["ts"] <= val_end else "test"
        parts[part].append(row)
    return parts, {"train_end_utc": train_end.isoformat(), "val_end_utc": val_end.isoformat()}


@dataclass
class StandardScaler:
    means: list[float]
    stds: list[float]

    @classmethod
    def fit(cls, rows: list[dict]):
        values = [r["values"] for r in rows if r["usable"]]
        if not values:
            raise ValueError("No train data to fit scaler")
        cols = list(zip(*values))
        means = [sum(col) / len(col) for col in cols]
        stds = [max(math.sqrt(sum((v-m)**2 for v in col) / len(col)), 1e-8) for col, m in zip(cols, means)]
        return cls(means, stds)

    def transform(self, values):
        return [(float(v) - m) / s for v, m, s in zip(values, self.means, self.stds)]

    def as_dict(self):
        return {"features": list(FEATURES), "mean": self.means, "std": self.stds, "fitted_on": "train_minutes_only"}


def make_windows(rows: list[dict], lookback=60, horizon=15):
    """Target is t+15 relative to LAST input (input ends at index lookback-1).

    Every intermediate minute through the target must be usable and consecutive.
    Returns list of (X, y, input_last, target_time, last_co2).
    """
    if lookback < 1 or horizon < 1:
        raise ValueError("lookback and horizon must be >= 1")
    windows = []
    size = lookback + horizon
    for start in range(0, len(rows) - size + 1):
        segment = rows[start:start+size]
        if not all(r["usable"] for r in segment):
            continue
        if any(b["ts"] - a["ts"] != timedelta(minutes=1) for a, b in zip(segment, segment[1:])):
            continue
        inputs = [r["values"] for r in segment[:lookback]]
        last = segment[lookback-1]
        target = segment[-1]
        windows.append((inputs, target["values"][0], last["ts"], target["ts"], last["values"][0]))
    return windows


def evaluate(y_true, y_pred):
    if not y_true:
        return None
    n = len(y_true)
    residuals = [a-b for a,b in zip(y_true, y_pred)]
    mae = sum(abs(x) for x in residuals) / n
    rmse = math.sqrt(sum(x*x for x in residuals) / n)
    avg = sum(y_true) / n
    denom = sum((v-avg)**2 for v in y_true)
    r2 = 1 - sum(x*x for x in residuals) / denom if denom > 0 else None
    return {"n": n, "MAE_ppm": round(mae, 4), "RMSE_ppm": round(rmse, 4), "R2": round(r2, 4) if r2 is not None else None}


def train(args):
    rows = load_minutes(Path(args.input))
    parts, boundaries = split_by_usable_time(rows)
    windows = {split: make_windows(part, args.lookback, args.horizon) for split, part in parts.items()}
    scaler = StandardScaler.fit(parts["train"])
    counts = {k: len(windows[k]) for k in windows}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "input": str(Path(args.input).resolve()),
        "dataset_type": "development; NOT official GD525 research data" if "development" in str(args.input) else "verify_data_provenance",
        "lookback_minutes": args.lookback,
        "horizon_minutes": args.horizon,
        "feature_order": list(FEATURES),
        "split_method": "chronological usable minute boundaries before windowing; no window crosses splits",
        "boundaries": boundaries,
        "usable_minutes_by_split": {k: sum(r["usable"] for r in v) for k,v in parts.items()},
        "windows_by_split": counts,
        "baseline_persistence": {},
        "GRU": None,
    }
    for k, examples in windows.items():
        report["baseline_persistence"][k] = evaluate([w[1] for w in examples], [w[4] for w in examples])
    (output / "scaler.json").write_text(json.dumps(scaler.as_dict(), indent=2), encoding="utf-8")

    if min(counts.values()) < args.min_windows:
        report["status"] = "insufficient_windows"
        report["message"] = (f"Require >= {args.min_windows} windows in EACH train/val/test split. "
                             "Continue collection; do not claim GRU performance from tiny development data.")
        (output / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    # Keep PyTorch optional until enough data is available; install explicitly in ML venv.
    try:
        import torch
        from torch import nn
    except ImportError:
        report["status"] = "torch_not_installed"
        report["message"] = "Install PyTorch in an ML virtualenv to train GRU; baseline report was saved."
        (output / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device(args.device)

    def tensors(samples):
        X = torch.tensor([[scaler.transform(row) for row in w[0]] for w in samples], dtype=torch.float32, device=device)
        # Standardize target with training CO2 mean/std only.
        y = torch.tensor([(w[1]-scaler.means[0])/scaler.stds[0] for w in samples], dtype=torch.float32, device=device)
        return X, y

    data = {k: tensors(v) for k, v in windows.items()}

    class GRURegressor(nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = nn.GRU(input_size=4, hidden_size=args.hidden, num_layers=1, batch_first=True)
            self.head = nn.Linear(args.hidden, 1)

        def forward(self, x):
            out, _ = self.gru(x)
            return self.head(out[:, -1, :]).squeeze(-1)

    model = GRURegressor().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.MSELoss()
    best_loss = float("inf")
    best_state = None
    patience = 0
    epochs_used = 0
    for epoch in range(args.epochs):
        model.train()
        Xtrain, ytrain = data["train"]
        order = torch.randperm(len(Xtrain), device=device)
        for ix in order.split(args.batch_size):
            optimizer.zero_grad()
            loss = criterion(model(Xtrain[ix]), ytrain[ix])
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            Xval, yval = data["val"]
            val_loss = criterion(model(Xval), yval).item()
        epochs_used = epoch + 1
        if val_loss < best_loss - 1e-7:
            best_loss = val_loss
            best_state = copy.deepcopy(model.state_dict())
            patience = 0
        else:
            patience += 1
            if patience >= args.patience:
                break

    model.load_state_dict(best_state)
    model.eval()
    pred_metrics = {}
    with torch.no_grad():
        for name, (X, y) in data.items():
            prediction = model(X).cpu().tolist()
            raw_pred = [v*scaler.stds[0] + scaler.means[0] for v in prediction]
            pred_metrics[name] = evaluate([w[1] for w in windows[name]], raw_pred)
    torch.save({"state_dict": best_state, "model": "GRURegressor", "input_size": 4,
                "hidden_size": args.hidden, "lookback": args.lookback, "horizon": args.horizon,
                "features": FEATURES, "scaler": scaler.as_dict()}, output / "gru_checkpoint.pt")
    report["status"] = "trained_development_experiment"
    report["GRU"] = {"epochs_trained": epochs_used, "best_validation_mse_normalized": best_loss, "metrics": pred_metrics,
                     "architecture": {"layers": 1, "hidden_units": args.hidden}, "device": str(device)}
    (output / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--lookback", type=int, default=60)
    parser.add_argument("--horizon", type=int, default=15)
    parser.add_argument("--min-windows", type=int, default=20)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--hidden", type=int, default=32)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    return train(args)


if __name__ == "__main__":
    raise SystemExit(main())
