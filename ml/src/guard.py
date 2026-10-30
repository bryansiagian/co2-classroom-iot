"""Pengaman agar data/model demo tidak bocor ke mode riil."""
from __future__ import annotations

import json
from pathlib import Path


def _has_demo_part(path: Path) -> bool:
    return "demo" in {part.lower() for part in Path(path).parts}


def assert_mode_safe(mode: str, *files_or_dirs: Path) -> None:
    """Di mode riil, tolak jika ada berkas/folder yang berada di jalur 'demo'."""
    if mode != "real":
        return
    for f in files_or_dirs:
        if _has_demo_part(Path(f)):
            raise SystemExit(
                f"DITOLAK: mode 'real' tidak boleh memakai berkas dari folder demo: {f}"
            )


def assert_meta_matches(mode: str, meta_path: Path) -> None:
    """Pastikan model yang dimuat dilatih pada mode yang sama."""
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    trained = meta.get("data_mode")
    if trained != mode:
        raise SystemExit(
            f"DITOLAK: model dilatih pada mode '{trained}', tetapi sekarang mode '{mode}'."
        )
