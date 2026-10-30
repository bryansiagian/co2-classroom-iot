"""Langkah 7: grafik prediksi vs aktual + evaluasi proaktif vs reaktif.

Definisi:
- Reaktif : alarm baru berbunyi saat CO2 aktual mencapai ambang (lead time = 0).
- Proaktif: peringatan dikeluarkan pada waktu t bila prediksi CO2(t+15) >= ambang,
            padahal CO2 aktual pada t masih di bawah ambang.
- Episode : awal menit ketika CO2 aktual naik melewati ambang (menit sebelumnya < ambang).
- Terdeteksi: ada peringatan pada [s-15, s-1] menit sebelum episode mulai di menit s.
  lead time = s - waktu peringatan paling awal pada rentang itu.
- Peringatan palsu: kejadian peringatan (menit berurutan digabung) yang tidak diikuti
  CO2 aktual >= ambang dalam 15 menit sesudahnya.

Contoh:
    python -m src.evaluate --models gru lstm persistence
"""
from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config, metrics
from .guard import assert_meta_matches, assert_mode_safe


def load_preds(models_dir, name):
    z = np.load(models_dir / name / "test_predictions.npz")
    return z["pred"], z["actual"], pd.to_datetime(z["t_end"])


def proactive_eval(co2: pd.Series, t_end: pd.DatetimeIndex, pred15: np.ndarray, thr: float, h: int = config.HORIZON) -> dict:
    co2 = co2.asfreq(f"{config.STEP_MIN}min")
    t0, t1 = t_end.min(), t_end.max() + pd.Timedelta(minutes=h)
    sub = co2.loc[t0:t1]

    alert = pd.Series(False, index=sub.index)
    a_idx = pd.Series(pred15 >= thr, index=t_end)
    alert.loc[a_idx.index] = a_idx.to_numpy()
    covered = pd.Series(False, index=sub.index)  # waktu yang punya prediksi
    covered.loc[t_end] = True

    below_now = sub < thr
    alert_pre = alert & below_now  # peringatan hanya bila aktual belum melewati ambang

    # --- episode aktual ---
    prev = sub.shift(1)
    starts = sub.index[(sub >= thr) & (prev < thr)]
    starts = [s for s in starts if s - pd.Timedelta(minutes=h) >= t0]

    leads, missed = [], 0
    for s in starts:
        win = alert_pre.loc[s - pd.Timedelta(minutes=h) : s - pd.Timedelta(minutes=1)]
        hits = win[win].index
        if len(hits):
            leads.append((s - hits.min()).total_seconds() / 60.0)
        else:
            missed += 1

    # --- kejadian peringatan & peringatan palsu ---
    grp = (alert_pre != alert_pre.shift()).cumsum()
    n_events, n_false = 0, 0
    for _, seg in alert_pre.groupby(grp):
        if not seg.iloc[0]:
            continue
        n_events += 1
        end = seg.index[-1]
        fut = sub.loc[seg.index[0] + pd.Timedelta(minutes=1) : end + pd.Timedelta(minutes=h)]
        if not (fut >= thr).any():
            n_false += 1

    n_ep = len(starts)
    return {
        "threshold_ppm": thr,
        "episodes": n_ep,
        "detected": len(leads),
        "missed": missed,
        "detection_rate_pct": round(100.0 * len(leads) / n_ep, 1) if n_ep else np.nan,
        "lead_mean_min": round(float(np.mean(leads)), 1) if leads else np.nan,
        "lead_median_min": round(float(np.median(leads)), 1) if leads else np.nan,
        "reactive_lead_min": 0.0,
        "alert_events": n_events,
        "false_alarms": n_false,
        "false_alarm_pct": round(100.0 * n_false / n_events, 1) if n_events else np.nan,
    }


def plot_pred_vs_actual(name, pred, actual, t_end, out_png, mode, days=3.0):
    t = pd.DatetimeIndex(t_end)
    # waktu target = t + 15 menit
    tt = t + pd.Timedelta(minutes=config.HORIZON)
    n = int(days * 24 * 60)
    fig, ax = plt.subplots(2, 1, figsize=(12, 7))
    ax[0].plot(tt[:n], actual[:n, -1], label="aktual", lw=1.2)
    ax[0].plot(tt[:n], pred[:n, -1], label=f"prediksi t+15 ({name})", lw=1.0)
    for th in config.THRESHOLDS_PPM:
        ax[0].axhline(th, color="grey", ls=":", lw=0.8)
    ax[0].set_ylabel("CO2 (ppm)")
    ax[0].set_title(f"{name}: prediksi vs aktual (data uji, {days:g} hari pertama)" + ("  [DATA DEMO]" if mode == "demo" else ""))
    ax[0].legend()
    ax[1].scatter(actual[:, -1], pred[:, -1], s=3, alpha=0.3)
    lim = [min(actual[:, -1].min(), pred[:, -1].min()), max(actual[:, -1].max(), pred[:, -1].max())]
    ax[1].plot(lim, lim, "r--", lw=1)
    ax[1].set_xlabel("aktual t+15 (ppm)")
    ax[1].set_ylabel("prediksi t+15 (ppm)")
    fig.tight_layout()
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


def plot_horizon(curves: dict[str, pd.DataFrame], out_png, mode):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, d in curves.items():
        ax.plot(range(1, len(d) + 1), d["RMSE"], marker="o", ms=3, label=name)
    ax.set_xlabel("langkah horizon (menit ke depan)")
    ax.set_ylabel("RMSE (ppm)")
    ax.set_title("RMSE per langkah horizon" + ("  [DATA DEMO]" if mode == "demo" else ""))
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluasi dan grafik")
    ap.add_argument("--mode", default=None)
    ap.add_argument("--models", nargs="+", default=["gru", "lstm", "persistence"])
    ap.add_argument("--days", type=float, default=3.0)
    a = ap.parse_args()
    mode = config.get_mode(a.mode)
    p = config.paths(mode)
    assert_mode_safe(mode, p["models_dir"], p["processed_dir"])

    clean = pd.read_csv(p["processed_dir"] / "clean.csv", parse_dates=["timestamp"]).set_index("timestamp")
    co2 = clean[config.TARGET]

    curves, rows = {}, []
    for name in a.models:
        d = p["models_dir"] / name
        if not (d / "test_predictions.npz").exists():
            print(f"[lewati] {name}: belum ada prediksi uji. Jalankan src.train dulu.")
            continue
        if (d / "meta.json").exists():
            assert_meta_matches(mode, d / "meta.json")
        pred, actual, t_end = load_preds(p["models_dir"], name)
        plot_pred_vs_actual(name, pred, actual, t_end, p["reports_dir"] / f"pred_vs_actual_{name}.png", mode, a.days)
        curves[name] = metrics.per_horizon(actual, pred)
        for thr in config.THRESHOLDS_PPM:
            r = proactive_eval(co2, t_end, pred[:, -1], thr)
            rows.append({"model": name, **r})

    if curves:
        plot_horizon(curves, p["reports_dir"] / "rmse_per_horizon.png", mode)
    res = pd.DataFrame(rows)
    res.to_csv(p["reports_dir"] / "proactive_vs_reactive.csv", index=False)

    md = [f"# Evaluasi proaktif vs reaktif (mode: {mode})", ""]
    if mode == "demo":
        md += ["> **DATA DEMO** — bukan hasil TA.", ""]
    md += [
        "Reaktif = alarm saat CO2 aktual melewati ambang (lead time 0 menit).",
        "Proaktif = peringatan saat prediksi t+15 melewati ambang.",
        "",
    ]
    if len(res):
        md.append("| " + " | ".join(res.columns) + " |")
        md.append("|" + "---|" * len(res.columns))
        for _, r in res.iterrows():
            md.append("| " + " | ".join(str(v) for v in r.tolist()) + " |")
    (p["reports_dir"] / "proactive_vs_reactive.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nGrafik dan tabel di {p['reports_dir']}")


if __name__ == "__main__":
    main()
