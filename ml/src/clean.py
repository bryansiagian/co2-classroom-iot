"""Langkah 4: bersihkan dan rapikan ke grid 1 menit.

Aturan:
- timestamp duplikat: ambil yang terakhir
- nilai di luar rentang valid -> NaN
- resample ke 1 menit (rata-rata; PIR memakai maksimum)
- celah <= MAX_GAP_MIN menit diisi interpolasi linear (PIR: nilai terakhir) dan ditandai
  di kolom filled_<nama>. Celah lebih panjang dibiarkan NaN.
Keluaran: data/processed/<mode>/clean.csv + reports/<mode>/clean.md
"""
from __future__ import annotations

import argparse
import math

import numpy as np
import pandas as pd

from . import config
from .guard import assert_mode_safe
from .load_data import load_mapped


def _fill_short_gaps(s: pd.Series, max_gap: int, ffill_only: bool = False) -> tuple[pd.Series, pd.Series]:
    isna = s.isna()
    run_id = (isna != isna.shift()).cumsum()
    run_len = isna.groupby(run_id).transform("sum")
    interior = s.ffill().notna() & s.bfill().notna()
    fillable = isna & (run_len <= max_gap) & interior
    if ffill_only:
        filled_vals = s.ffill()
    else:
        filled_vals = s.interpolate(method="linear", limit_area="inside")
    out = s.copy()
    out[fillable] = filled_vals[fillable]
    return out, fillable


def clean(df: pd.DataFrame, max_gap_min: int = config.MAX_GAP_MIN) -> tuple[pd.DataFrame, dict]:
    info: dict = {"rows_in": int(len(df))}
    df = df.sort_values("timestamp")

    n_dup = int(df["timestamp"].duplicated(keep="last").sum())
    df = df.drop_duplicates(subset="timestamp", keep="last")
    info["duplicates_removed"] = n_dup

    oor = {}
    for col, (lo, hi) in config.VALID_RANGE.items():
        if col in df.columns:
            bad = (df[col] < lo) | (df[col] > hi)
            oor[col] = int(bad.sum())
            df.loc[bad, col] = np.nan
    info["out_of_range_to_nan"] = oor

    diffs = df["timestamp"].diff().dropna().dt.total_seconds()
    median_s = float(diffs.median()) if len(diffs) else 60.0
    info["median_interval_s"] = median_s

    eff_gap = max_gap_min
    if median_s > 90:
        # data lebih jarang dari 1 menit: beri toleransi sebesar jarak sampel normal
        eff_gap = int(math.ceil(median_s / 60.0)) - 1 + max_gap_min
        info["warning"] = (
            f"Interval median {median_s:.0f} detik (> 1 menit): data di-upsample ke 1 menit "
            f"dan toleransi celah dinaikkan menjadi {eff_gap} menit. Pertimbangkan memakai "
            "resolusi asli untuk model."
        )
    info["effective_max_gap_min"] = eff_gap

    cols = [c for c in df.columns if c != "timestamp"]
    agg = {c: ("max" if c == "pir" else "mean") for c in cols}
    g = df.set_index("timestamp").resample(f"{config.STEP_MIN}min").agg(agg)

    filled_counts = {}
    for c in cols:
        g[c], mask = _fill_short_gaps(g[c], eff_gap, ffill_only=(c == "pir"))
        g[f"filled_{c}"] = mask.astype(int)
        filled_counts[c] = int(mask.sum())
    info["filled_counts"] = filled_counts

    # statistik celah tersisa pada target
    na = g[config.TARGET].isna()
    run_id = (na != na.shift()).cumsum()
    runs = na.groupby(run_id).agg(["first", "sum"])
    remaining = runs[runs["first"]]["sum"]
    info["remaining_gaps_target"] = {
        "count": int(len(remaining)),
        "longest_min": int(remaining.max()) if len(remaining) else 0,
    }
    info["rows_out"] = int(len(g))
    info["rows_valid_target"] = int((~na).sum())
    return g.reset_index(), info


def report_md(info: dict, mode: str) -> str:
    L = [f"# Laporan pembersihan (mode: {mode})", ""]
    for k, v in info.items():
        L.append(f"- **{k}**: {v}")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Bersihkan data dan rapikan ke 1 menit")
    ap.add_argument("--mode", default=None)
    ap.add_argument("--file", default=None)
    ap.add_argument("--max-gap", type=int, default=config.MAX_GAP_MIN)
    a = ap.parse_args()
    mode = config.get_mode(a.mode)
    p = config.paths(mode)

    df, raw_path, _ = load_mapped(mode, a.file)
    out, info = clean(df, a.max_gap)
    out_path = p["processed_dir"] / "clean.csv"
    assert_mode_safe(mode, out_path)
    out.to_csv(out_path, index=False)
    md = report_md({"source": raw_path.name, **info}, mode)
    (p["reports_dir"] / "clean.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"Dataset bersih: {out_path}")


if __name__ == "__main__":
    main()
