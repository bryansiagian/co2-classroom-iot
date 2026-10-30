"""Langkah 3: audit kualitas data. Keluaran: reports/<mode>/audit.md + audit.json"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from . import config
from .load_data import load_mapped


def run_audit(df: pd.DataFrame, missing_cols: list[str]) -> dict:
    ts = df["timestamp"]
    diffs = ts.diff().dropna().dt.total_seconds()
    median_s = float(diffs.median()) if len(diffs) else float("nan")

    dup_ts = int(ts.duplicated().sum())
    gaps = diffs[diffs > max(median_s * 1.5, 1.0)]
    gap_min = (gaps / 60.0)

    out_of_range = {}
    for col, (lo, hi) in config.VALID_RANGE.items():
        if col in df.columns:
            s = df[col]
            out_of_range[col] = int(((s < lo) | (s > hi)).sum())

    nan_counts = {c: int(df[c].isna().sum()) for c in df.columns if c != "timestamp"}
    stats = (
        df.drop(columns=["timestamp"]).describe().T[["mean", "std", "min", "50%", "max"]].round(2)
    )

    total_span_min = (ts.max() - ts.min()).total_seconds() / 60.0
    expected_rows = total_span_min * 60.0 / median_s + 1 if median_s > 0 else float("nan")

    return {
        "rows": int(len(df)),
        "start": str(ts.min()),
        "end": str(ts.max()),
        "span_hours": round(total_span_min / 60.0, 2),
        "median_interval_s": median_s,
        "interval_p95_s": float(diffs.quantile(0.95)) if len(diffs) else None,
        "completeness_pct": round(100.0 * len(df) / expected_rows, 2) if expected_rows else None,
        "duplicate_timestamps": dup_ts,
        "n_gaps": int(len(gaps)),
        "gap_minutes": {
            "max": round(float(gap_min.max()), 2) if len(gap_min) else 0.0,
            "median": round(float(gap_min.median()), 2) if len(gap_min) else 0.0,
            "n_le_3min": int((gap_min <= config.MAX_GAP_MIN).sum()),
            "n_gt_3min": int((gap_min > config.MAX_GAP_MIN).sum()),
        },
        "missing_columns": missing_cols,
        "nan_counts": nan_counts,
        "out_of_range": out_of_range,
        "needs_resample_to_1min": bool(abs(median_s - 60.0) > 1.0),
        "stats": stats.reset_index().rename(columns={"index": "kolom"}).to_dict("records"),
    }


def to_markdown(a: dict, mode: str, source: str) -> str:
    L = [f"# Audit kualitas data (mode: {mode})", "", f"Sumber: `{source}`", ""]
    L += [
        f"- Baris: **{a['rows']}**",
        f"- Rentang: {a['start']} -> {a['end']} ({a['span_hours']} jam)",
        f"- Interval median: **{a['median_interval_s']:.1f} detik** (p95: {a['interval_p95_s']:.1f} detik)",
        f"- Kelengkapan terhadap interval median: {a['completeness_pct']}%",
        f"- Timestamp duplikat: {a['duplicate_timestamps']}",
        f"- Celah (lebih dari 1,5x interval): {a['n_gaps']} "
        f"(maks {a['gap_minutes']['max']} menit; <=3 menit: {a['gap_minutes']['n_le_3min']}; "
        f">3 menit: {a['gap_minutes']['n_gt_3min']})",
        f"- Kolom tidak ada di dataset: {a['missing_columns'] or '-'}",
        f"- Perlu resample ke 1 menit: **{'ya' if a['needs_resample_to_1min'] else 'tidak'}**",
        "",
        "## NaN per kolom",
        "",
        "| kolom | NaN |",
        "|---|---|",
    ]
    L += [f"| {k} | {v} |" for k, v in a["nan_counts"].items()]
    L += ["", "## Nilai di luar rentang valid", "", "| kolom | jumlah |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in a["out_of_range"].items()]
    L += ["", "## Statistik dasar", "", "| kolom | mean | std | min | median | max |", "|---|---|---|---|---|---|"]
    for r in a["stats"]:
        L.append(f"| {r['kolom']} | {r['mean']} | {r['std']} | {r['min']} | {r['50%']} | {r['max']} |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit kualitas data")
    ap.add_argument("--mode", default=None)
    ap.add_argument("--file", default=None)
    args = ap.parse_args()
    mode = config.get_mode(args.mode)
    p = config.paths(mode)

    df, raw_path, missing = load_mapped(mode, args.file)
    a = run_audit(df, missing)
    (p["reports_dir"] / "audit.json").write_text(json.dumps(a, indent=2, ensure_ascii=False), encoding="utf-8")
    md = to_markdown(a, mode, raw_path.name)
    (p["reports_dir"] / "audit.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"Laporan disimpan di {p['reports_dir']}")


if __name__ == "__main__":
    main()
