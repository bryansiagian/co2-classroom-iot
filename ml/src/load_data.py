"""Langkah 2: muat dataset mentah (CSV/XLSX) dan petakan kolom ke kontrak data."""
from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path

import pandas as pd

from . import config
from .guard import assert_mode_safe

SUPPORTED = (".csv", ".xlsx", ".xls")


def find_raw_file(raw_dir: Path, explicit: str | None = None) -> Path:
    if explicit:
        f = Path(explicit)
        if not f.exists():
            raise SystemExit(f"Berkas tidak ditemukan: {f}")
        return f
    files = sorted(p for p in raw_dir.iterdir() if p.suffix.lower() in SUPPORTED)
    if not files:
        raise SystemExit(
            f"Tidak ada CSV/XLSX di {raw_dir}. Taruh dataset di sana, "
            "atau jalankan: python -m src.make_demo_data"
        )
    if len(files) > 1:
        print(f"[peringatan] ada {len(files)} berkas, memakai yang pertama: {files[0].name}")
    return files[0]


def _decode(path: Path) -> tuple[str, str]:
    """Baca byte file lalu decode: UTF-16 (BOM), UTF-8, Windows-1252, terakhir Latin-1."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise SystemExit("Encoding CSV tidak dikenali.")


def _pick_delimiter(header: str) -> str:
    counts = {d: header.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=counts.get)
    if counts[best] == 0:
        raise SystemExit(
            "Pemisah kolom tidak terdeteksi pada baris pertama. "
            f"Isi baris pertama: {header[:120]!r}"
        )
    return best


def _sniff_kind(path: Path) -> str:
    """Tentukan jenis file dari ISI (bukan dari ekstensi): xlsx, xls, atau csv."""
    head = path.read_bytes()[:8]
    if head.startswith(b"PK\x03\x04"):
        return "xlsx"  # arsip zip = Excel modern, walau ekstensinya .csv
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"   # Excel lama
    return "csv"


def _read_csv_text(path: Path) -> pd.DataFrame:
    text, enc = _decode(path)
    # Buang semua tanda kutip (kutip pembungkus baris / kutip nyasar), samakan akhir baris
    text = text.replace('"', "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if lines and lines[0].strip().lower().startswith("sep="):  # petunjuk Excel
        lines = lines[1:]
    if not lines:
        raise SystemExit("File CSV kosong.")
    sep = _pick_delimiter(lines[0])
    sample = "\n".join(lines[1:200])
    decimal = "."
    if sep != "," and re.search(r"\d,\d", sample) and not re.search(r"\d\.\d", sample):
        decimal = ","
    print(f"[info] CSV: encoding={enc} pemisah={sep!r} desimal={decimal!r} baris={len(lines) - 1}")
    return pd.read_csv(
        io.StringIO("\n".join(lines)),
        sep=sep,
        decimal=decimal,
        engine="python",
        on_bad_lines="warn",
    )


def read_raw(path: Path) -> pd.DataFrame:
    kind = _sniff_kind(path)
    if kind == "xlsx":
        if path.suffix.lower() != ".xlsx":
            print(f"[info] {path.name} sebenarnya file Excel (.xlsx), dibaca sebagai Excel.")
        df = pd.read_excel(path, engine="openpyxl")  # sheet pertama
    elif kind == "xls":
        try:
            df = pd.read_excel(path, engine="xlrd")
        except ImportError:
            raise SystemExit(
                "File Excel lama (.xls) butuh paket xlrd: python -m pip install xlrd "
                "(atau simpan ulang sebagai .xlsx)."
            )
    else:
        df = _read_csv_text(path)
    # rapikan nama kolom (spasi di awal/akhir)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_column_map(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_mapping(raw: pd.DataFrame, cmap: dict) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Kembalikan (df berkolom kontrak, kolom_hilang, kolom_dibuang_dari_fitur)."""
    out = pd.DataFrame()
    missing: list[str] = []
    for col in config.CONTRACT_COLS:
        src = cmap.get(col)
        if src is None:
            missing.append(col)
            continue
        if src not in raw.columns:
            raise SystemExit(
                f"Kolom '{src}' (untuk '{col}') tidak ada di dataset. "
                f"Kolom tersedia: {list(raw.columns)}. Perbaiki column_map.json."
            )
        out[col] = raw[src]
    for must in ("timestamp", config.TARGET):
        if must in missing:
            raise SystemExit(f"Kolom wajib '{must}' belum dipetakan di column_map.json.")

    out["timestamp"] = pd.to_datetime(
        out["timestamp"], format=cmap.get("_timestamp_format"), errors="coerce"
    )
    tz = cmap.get("_timezone")
    if tz:
        out["timestamp"] = out["timestamp"].dt.tz_localize(tz).dt.tz_convert(None)
    n_bad_ts = int(out["timestamp"].isna().sum())
    if n_bad_ts:
        print(f"[peringatan] {n_bad_ts} baris timestamp tidak terbaca, dibuang.")
        out = out.dropna(subset=["timestamp"])
    for col in out.columns:
        if col != "timestamp":
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out, missing, [c for c in config.FEATURE_CANDIDATES if c in missing]


def load_mapped(mode: str, file: str | None = None) -> tuple[pd.DataFrame, Path, list[str]]:
    p = config.paths(mode)
    raw_path = find_raw_file(p["raw_dir"], file)
    assert_mode_safe(mode, raw_path)
    raw = read_raw(raw_path)
    cmap = load_column_map(p["column_map"])
    df, missing, _ = apply_mapping(raw, cmap)
    return df, raw_path, missing


def main() -> None:
    ap = argparse.ArgumentParser(description="Muat dataset dan cek pemetaan kolom")
    ap.add_argument("--mode", default=None)
    ap.add_argument("--file", default=None)
    a = ap.parse_args()
    mode = config.get_mode(a.mode)
    df, raw_path, missing = load_mapped(mode, a.file)
    print(f"Mode        : {mode}")
    print(f"Berkas      : {raw_path}")
    print(f"Baris       : {len(df)}")
    print(f"Rentang     : {df['timestamp'].min()} -> {df['timestamp'].max()}")
    print(f"Kolom ada   : {[c for c in df.columns]}")
    print(f"Kolom absen : {missing}")
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()