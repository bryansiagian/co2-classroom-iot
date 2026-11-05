#!/usr/bin/env python3
"""Build timestamp-continuous multivariate windows from GD525 all_minutes.csv.

Pure Python; does not modify SQLite or raw CSV. Every minute from the first
input observation through the target must be usable and exactly 1 minute apart.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / 'ml/data/processed/development/all_minutes.csv'
DEFAULT_OUTPUT = REPO_ROOT / 'ml/data/processed/development/windows'
FEATURES = ('co2_ppm', 'temp_in_c', 'hum_in_pct', 'pir')
INDEX_FIELDS = ('window_id', 'input_start_utc', 'input_end_utc', 'target_utc', 'target_co2_ppm')


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timestamp tidak memiliki timezone')
    dt = dt.astimezone(timezone.utc)
    if dt.second or dt.microsecond:
        raise ValueError('timestamp tidak berada di batas menit')
    return dt


def load_minutes(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f'CSV tidak ditemukan: {path}')
    result = []
    with path.open(newline='', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        required = {'minute_utc', 'status', *FEATURES}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f'Kolom CSV wajib: {sorted(required)}')
        for number, row in enumerate(reader, start=2):
            try:
                ts = parse_utc(row['minute_utc'])
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f'Baris {number}: timestamp invalid: {exc}') from exc
            usable = row['status'] == 'usable'
            features = None
            if usable:
                try:
                    features = [float(row[name]) for name in FEATURES]
                except (TypeError, ValueError) as exc:
                    raise ValueError(f'Baris {number}: fitur usable invalid: {exc}') from exc
                if not all(math.isfinite(x) for x in features):
                    raise ValueError(f'Baris {number}: fitur usable non-finite')
                if features[3] not in (0, 1):
                    raise ValueError(f'Baris {number}: PIR bukan 0/1')
            result.append({'ts': ts, 'usable': usable, 'x': features})
    for prev, curr in zip(result, result[1:]):
        if prev['ts'] >= curr['ts']:
            raise ValueError('CSV harus urut waktu naik dan timestamp unik')
    return result


def split_segments(minutes: list[dict]) -> list[list[dict]]:
    segments = []
    current = []
    for row in minutes:
        if not row['usable']:
            if current:
                segments.append(current)
                current = []
            continue
        if current and row['ts'] - current[-1]['ts'] != timedelta(minutes=1):
            segments.append(current)
            current = []
        current.append(row)
    if current:
        segments.append(current)
    return segments


def generate_windows(minutes: list[dict], lookback: int = 60, horizon: int = 15,
                     stride: int = 1) -> list[dict]:
    if min(lookback, horizon, stride) < 1:
        raise ValueError('lookback, horizon, dan stride harus >= 1')
    windows = []
    for segment in split_segments(minutes):
        # Input has lookback points ending at t; target is exactly t+horizon.
        required = lookback + horizon
        for start in range(0, len(segment) - required + 1, stride):
            inputs = segment[start:start + lookback]
            target = segment[start + lookback + horizon - 1]
            windows.append({
                'window_id': len(windows) + 1,
                'input_start_utc': inputs[0]['ts'].isoformat().replace('+00:00', 'Z'),
                'input_end_utc': inputs[-1]['ts'].isoformat().replace('+00:00', 'Z'),
                'target_utc': target['ts'].isoformat().replace('+00:00', 'Z'),
                'features': list(FEATURES),
                'X': [row['x'] for row in inputs],
                'y_co2_ppm': target['x'][0],
            })
    return windows


def build_report(minutes: list[dict], windows: list[dict], lookback: int,
                 horizon: int, stride: int, source: Path) -> dict:
    segments = split_segments(minutes)
    return {
        'source_csv': str(source.resolve()),
        'dataset_type': 'development (jangan digunakan sebagai data resmi GD525)',
        'feature_order': list(FEATURES),
        'input_minutes': lookback,
        'target_horizon_minutes': horizon,
        'stride_minutes': stride,
        'total_minute_rows': len(minutes),
        'usable_minute_rows': sum(row['usable'] for row in minutes),
        'continuous_segments': len(segments),
        'longest_segment_minutes': max((len(s) for s in segments), default=0),
        'windows_created': len(windows),
        'first_target_utc': windows[0]['target_utc'] if windows else None,
        'last_target_utc': windows[-1]['target_utc'] if windows else None,
        'warnings': [
            'Semua menit dari awal input hingga target harus usable; tidak ada interpolasi.',
            'Belum ada train/validation/test split maupun normalisasi; lakukan split kronologis sebelum fitting scaler.',
            'Windows yang overlap tidak boleh dibagi secara acak antar train/validation/test.',
            'Timestamp bersumber dari waktu penerimaan backend (received_at UTC).',
        ],
    }


def export(input_path: Path, output_dir: Path, lookback: int, horizon: int, stride: int) -> dict:
    minutes = load_minutes(input_path)
    windows = generate_windows(minutes, lookback, horizon, stride)
    report = build_report(minutes, windows, lookback, horizon, stride, input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / 'windows.jsonl').open('w', encoding='utf-8') as file:
        for window in windows:
            file.write(json.dumps(window, ensure_ascii=False, separators=(',', ':')) + '\n')
    with (output_dir / 'windows_index.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        for window in windows:
            writer.writerow({**{k: window[k] for k in INDEX_FIELDS if k != 'target_co2_ppm'},
                             'target_co2_ppm': window['y_co2_ppm']})
    (output_dir / 'windows_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description='Build contiguous GD525 GRU training windows')
    parser.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--out-dir', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--lookback', type=int, default=60)
    parser.add_argument('--horizon', type=int, default=15)
    parser.add_argument('--stride', type=int, default=1)
    args = parser.parse_args()
    if min(args.lookback, args.horizon, args.stride) < 1:
        parser.error('--lookback, --horizon, --stride harus >= 1')
    report = export(args.input, args.out_dir, args.lookback, args.horizon, args.stride)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f'Output: {args.out_dir.resolve()}')


if __name__ == '__main__':
    main()
