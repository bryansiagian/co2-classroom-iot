import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.home() / "co2-classroom-iot"
SOURCE = ROOT / "backend/backend/data/co2class.db"
DEST_DIR = ROOT / "backups"

DEST_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
destination = DEST_DIR / f"co2class_{timestamp}.db"

with sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True) as source:
    with sqlite3.connect(destination) as backup:
        source.backup(backup)

print(f"Backup berhasil: {destination}")
