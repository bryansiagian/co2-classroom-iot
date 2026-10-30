"""Langkah 6: latih dan bandingkan Persistence, LSTM, GRU.

Contoh:
    python -m src.train                       # mode dari env DATA_MODE (default demo)
    python -m src.train --windows 15 30 60 --epochs 60
    python -m src.train --mode real

Keluaran (di models/<mode>/ dan reports/<mode>/):
    models/<mode>/<gru|lstm>/model.pt, scaler.json, meta.json, test_predictions.npz
    models/<mode>/persistence/test_predictions.npz
    reports/<mode>/comparison.csv, comparison.md, per_horizon_<model>.csv, history_<model>_N<w>.csv
"""
from __future__ import annotations

import argparse
import copy
import json
import time

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from . import config, metrics
from .guard import assert_mode_safe
from .models import Persistence, RNNForecaster, count_params
from .windows import Scaler, fit_scaler, make_windows, select_features, split_bounds


def set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def predict_ppm(model: nn.Module, X: np.ndarray, scaler: Scaler, device: str) -> np.ndarray:
    model.eval()
    outs = []
    with torch.no_grad():
        for i in range(0, len(X), 1024):
            xb = torch.from_numpy(X[i : i + 1024]).to(device)
            outs.append(model(xb).cpu().numpy())
    return scaler.inverse_target(np.concatenate(outs, axis=0))


def fit(model, Xtr, Ytr, Xva, Yva, epochs, batch, lr, patience, device):
    model.to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=max(2, patience // 3))
    loss_fn = nn.MSELoss()
    dl = DataLoader(
        TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(Ytr)),
        batch_size=batch,
        shuffle=True,
    )
    Xva_t = torch.from_numpy(Xva).to(device)
    Yva_t = torch.from_numpy(Yva).to(device)

    best, best_state, bad, hist = float("inf"), None, 0, []
    for ep in range(1, epochs + 1):
        model.train()
        tr_loss, n = 0.0, 0
        for xb, yb in dl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tr_loss += loss.item() * len(xb)
            n += len(xb)
        model.eval()
        with torch.no_grad():
            va_loss = loss_fn(model(Xva_t), Yva_t).item()
        sched.step(va_loss)
        hist.append({"epoch": ep, "train_loss": tr_loss / max(n, 1), "val_loss": va_loss})
        if va_loss < best - 1e-6:
            best, best_state, bad = va_loss, copy.deepcopy(model.state_dict()), 0
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    return pd.DataFrame(hist)


def main() -> None:
    ap = argparse.ArgumentParser(description="Latih dan bandingkan model")
    ap.add_argument("--mode", default=None)
    ap.add_argument("--windows", type=int, nargs="+", default=config.WINDOW_CANDIDATES)
    ap.add_argument("--models", nargs="+", default=["lstm", "gru"])
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=8)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=config.SEED)
    a = ap.parse_args()

    mode = config.get_mode(a.mode)
    p = config.paths(mode)
    clean_path = p["processed_dir"] / "clean.csv"
    assert_mode_safe(mode, clean_path, p["models_dir"])
    if not clean_path.exists():
        raise SystemExit(f"{clean_path} belum ada. Jalankan: python -m src.clean")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    set_seed(a.seed)
    df = pd.read_csv(clean_path, parse_dates=["timestamp"])
    features = select_features(df)
    bounds = split_bounds(len(df))
    scaler = fit_scaler(df, features, bounds["train"])  # hanya dari bagian train
    ti = features.index(config.TARGET)
    print(f"Mode={mode} device={device} fitur={features} baris={len(df)} split={bounds}")

    # --- bentuk jendela untuk tiap N dan tiap split -------------------------
    data = {}
    for N in a.windows:
        data[N] = {
            s: make_windows(df, features, scaler, N, row_range=bounds[s]) for s in ("train", "val", "test")
        }
        print(f"N={N}: " + ", ".join(f"{s}={len(data[N][s][0])}" for s in ("train", "val", "test")))
        if min(len(data[N][s][0]) for s in data[N]) == 0:
            raise SystemExit(f"Jendela N={N} kosong pada salah satu split. Data terlalu sedikit/bercelah.")

    # Bandingkan pada titik waktu uji yang sama untuk semua N
    common = {
        s: np.array(sorted(set.intersection(*[set(data[N][s][3].tolist()) for N in a.windows])))
        for s in ("val", "test")
    }

    def subset(N, split):
        X, Y, Yr, te = data[N][split]
        mask = np.isin(te, common[split])
        return X[mask], Y[mask], Yr[mask], te[mask]

    rows, best_by_kind = [], {}

    # --- Persistence -------------------------------------------------------
    N0 = a.windows[0]
    Xte, _, Yte_raw, te_test = subset(N0, "test")
    pers = Persistence(ti)
    p_pers = scaler.inverse_target(pers.predict(Xte))
    s = metrics.summary(Yte_raw, p_pers)
    rows.append({"model": "persistence", "N": N0, "params": 0, "val_RMSE_t15": np.nan, **s})
    pdir = p["models_dir"] / "persistence"
    pdir.mkdir(exist_ok=True)
    np.savez(pdir / "test_predictions.npz", pred=p_pers, actual=Yte_raw, t_end=te_test.astype("datetime64[ns]"))
    metrics.per_horizon(Yte_raw, p_pers).to_csv(p["reports_dir"] / "per_horizon_persistence.csv", index=False)

    # --- LSTM / GRU --------------------------------------------------------
    for kind in a.models:
        for N in a.windows:
            set_seed(a.seed)
            Xtr, Ytr, _, _ = data[N]["train"]
            Xva, Yva, Yva_raw, _ = subset(N, "val")
            Xte, _, Yte_raw, te_test = subset(N, "test")
            model = RNNForecaster(len(features), kind, a.hidden, a.layers, a.dropout)
            t0 = time.time()
            hist = fit(model, Xtr, Ytr, Xva, Yva, a.epochs, a.batch, a.lr, a.patience, device)
            dt = time.time() - t0
            pva = predict_ppm(model, Xva, scaler, device)
            pte = predict_ppm(model, Xte, scaler, device)
            val_rmse = metrics.rmse(Yva_raw[:, -1], pva[:, -1])
            s = metrics.summary(Yte_raw, pte)
            rows.append({"model": kind, "N": N, "params": count_params(model), "val_RMSE_t15": val_rmse, **s})
            hist.to_csv(p["reports_dir"] / f"history_{kind}_N{N}.csv", index=False)
            print(
                f"{kind.upper():5s} N={N:3d} epoch={len(hist):3d} val_RMSE_t15={val_rmse:7.1f} "
                f"test_RMSE_t15={s['RMSE_t15']:7.1f} R2_t15={s['R2_t15']:.3f} ({dt:.0f}s)"
            )
            if kind not in best_by_kind or val_rmse < best_by_kind[kind]["val_rmse"]:
                best_by_kind[kind] = {
                    "val_rmse": val_rmse,
                    "N": N,
                    "state": copy.deepcopy(model.state_dict()),
                    "pred": pte,
                    "actual": Yte_raw,
                    "t_end": te_test,
                    "history_epochs": len(hist),
                }

    # --- simpan model terbaik per jenis (dipilih dari RMSE VALIDASI) ---------
    for kind, b in best_by_kind.items():
        d = p["models_dir"] / kind
        d.mkdir(exist_ok=True)
        torch.save(b["state"], d / "model.pt")
        scaler.save(d / "scaler.json")
        meta = {
            "data_mode": mode,
            "framework": "pytorch",
            "kind": kind,
            "window": b["N"],
            "horizon": config.HORIZON,
            "features": features,
            "target": config.TARGET,
            "hidden": a.hidden,
            "layers": a.layers,
            "dropout": a.dropout,
            "step_min": config.STEP_MIN,
            "val_RMSE_t15": b["val_rmse"],
            "trained_on_rows": len(df),
            "torch_version": torch.__version__,
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        np.savez(d / "test_predictions.npz", pred=b["pred"], actual=b["actual"], t_end=b["t_end"].astype("datetime64[ns]"))
        metrics.per_horizon(b["actual"], b["pred"]).to_csv(p["reports_dir"] / f"per_horizon_{kind}.csv", index=False)

    # --- tabel perbandingan -------------------------------------------------
    res = pd.DataFrame(rows)
    res.to_csv(p["reports_dir"] / "comparison.csv", index=False)
    show = res.round(3)
    md = [f"# Perbandingan model (mode: {mode})", ""]
    if mode == "demo":
        md += ["> **DATA DEMO** — angka ini BUKAN hasil TA. Jangan masukkan ke laporan/slide.", ""]
    md += ["Metrik dihitung pada data uji (urut waktu, tidak dipakai saat pelatihan), dalam ppm.", ""]
    md.append("| " + " | ".join(show.columns) + " |")
    md.append("|" + "---|" * len(show.columns))
    for _, r in show.iterrows():
        md.append("| " + " | ".join(str(v) for v in r.tolist()) + " |")
    (p["reports_dir"] / "comparison.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n" + show.to_string(index=False))
    print(f"\nTersimpan di {p['models_dir']} dan {p['reports_dir']}")


if __name__ == "__main__":
    main()
