
"""Menerima pesan sensor: validasi, simpan, prediksi, rekomendasi.

Aturan validasi mengikuti docs/02-kontrak-data.md bagian 2.

Mendukung:
- Payload legacy ESP32 V4.2 dan sebelumnya.
- Payload ESP32 V4.3 dengan metadata boot dan pengukuran.
- Penyimpanan payload mentah untuk audit.
- Deduplikasi berdasarkan indeks SQLite.
- Penandaan kualitas data tanpa menghapus pembacaan suspect.

Catatan:
Database harus menggunakan schema V4.3 sebelum backend ini
dijalankan terhadap database utama.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3

from datetime import datetime, timedelta
from typing import Callable

from .config import Settings
from .db import Database
from .predictor import Predictor
from .recommend import recommend
from .timeutil import parse_iso, to_iso, utcnow


log = logging.getLogger("co2class.ingest")

CO2_RANGE = (350, 5000)
TEMP_RANGE = (-10, 60)
HUM_RANGE = (0, 100)

# Jumlah pembacaan, bukan durasi 60 menit.
# Resampling 1 menit akan diintegrasikan pada tahap GRU.
HISTORY_FOR_PREDICTOR = 60

Publisher = Callable[[str, dict], None]


def _num(value):
    """Mengambil angka finite, mengabaikan bool, NaN, dan infinity."""
    if type(value) not in (int, float):
        return None

    if not math.isfinite(value):
        return None

    return value


def _in(value, value_range) -> bool:
    """Periksa apakah angka berada dalam rentang yang ditentukan."""
    return (
        value is None
        or value_range[0] <= value <= value_range[1]
    )


def _nonnegative_int(value):
    """Mengembalikan integer >= 0 tanpa menerima boolean."""
    if type(value) is int and value >= 0:
        return value
    return None


class Pipeline:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        predictor: Predictor,
        publisher: Publisher | None = None,
    ):
        self.db = db
        self.s = settings
        self.predictor = predictor
        self.publisher = publisher

        # Pelacakan urutan pesan per device + sesi boot.
        # Hanya disimpan di memori selama backend berjalan.
        self._last_seq: dict[tuple[str, str | None], int] = {}

    # ============================================================
    # SENSOR INGESTION
    # ============================================================

    def handle_sensor_message(
        self,
        room_id: str,
        payload: bytes | str | dict,
        received_at: datetime | None = None,
    ) -> dict | None:
        """Validasi, simpan sensor, dan jalankan rekomendasi."""

        if received_at is None:
            received_at = utcnow()

        # Pertahankan payload asli.
        if isinstance(payload, str):
            raw = payload
        elif isinstance(payload, bytes):
            raw = payload.decode("utf-8", "replace")
        else:
            raw = json.dumps(payload, allow_nan=False)

        # --------------------------------------------------------
        # 1. PARSING JSON DAN ADAPTER LEGACY
        # --------------------------------------------------------

        try:
            msg = json.loads(raw)

            if not isinstance(msg, dict):
                raise ValueError("Payload harus berupa objek JSON")

            # Adapter payload pendek ESP32 V4.2.
            # **msg menjaga metadata tambahan jika tersedia.
            if {"co2", "temperature", "humidity", "pir"}.issubset(msg):
                msg = {
                    **msg,
                    "device_id": msg.get("device_id") or "esp32_gd525",
                    "co2_ppm": msg["co2"],
                    "temp_in_c": msg["temperature"],
                    "hum_in_pct": msg["humidity"],
                    "pir": msg["pir"],
                    "ts": msg.get("ts"),
                    "faults": msg.get("faults", []),
                }

            if (
                not isinstance(msg.get("device_id"), str)
                or not msg["device_id"].strip()
            ):
                raise ValueError("device_id wajib berupa string")

        except (ValueError, TypeError, UnicodeError) as exc:
            log.warning(
                "Pesan sensor ditolak (%s): %.120s",
                exc,
                raw,
            )
            return None

        device_id = msg["device_id"].strip()
        flags: list[str] = []

        # --------------------------------------------------------
        # 2. VALIDASI SENSOR
        # --------------------------------------------------------

        co2 = _num(msg.get("co2_ppm"))
        temp_in = _num(msg.get("temp_in_c"))
        hum_in = _num(msg.get("hum_in_pct"))
        temp_out = _num(msg.get("temp_out_c"))
        hum_out = _num(msg.get("hum_out_pct"))

        if not (
            _in(co2, CO2_RANGE)
            and _in(temp_in, TEMP_RANGE)
            and _in(temp_out, TEMP_RANGE)
            and _in(hum_in, HUM_RANGE)
            and _in(hum_out, HUM_RANGE)
        ):
            flags.append("suspect")

        pir_raw = msg.get("pir")
        pir = (
            int(pir_raw)
            if pir_raw in (0, 1, True, False)
            else None
        )

        faults = (
            msg.get("faults")
            if isinstance(msg.get("faults"), list)
            else []
        )

        rssi = _num(msg.get("rssi"))

        # --------------------------------------------------------
        # 3. METADATA V4.3
        # --------------------------------------------------------

        seq = _nonnegative_int(msg.get("seq"))

        boot_raw = msg.get("boot_id")
        boot_id = (
            boot_raw.strip()
            if isinstance(boot_raw, str) and boot_raw.strip()
            else None
        )

        uptime_ms = _nonnegative_int(msg.get("uptime_ms"))

        if boot_id is not None and seq is None:
            flags.append("sequence_missing")

        # Timestamp pengukuran aktual dari ESP32.
        measured_at_utc = None
        measured_raw = msg.get("measured_at_utc")

        if measured_raw is not None:
            if isinstance(measured_raw, str):
                try:
                    measured_at_utc = to_iso(parse_iso(measured_raw))
                except (ValueError, TypeError):
                    flags.append("measured_at_invalid")
            else:
                flags.append("measured_at_invalid")

        # --------------------------------------------------------
        # 4. TIMESTAMP EFEKTIF
        # --------------------------------------------------------

        # Gunakan measured_at_utc sebagai kandidat jika tersedia.
        # Jika tidak, tetap mendukung field ts dari kontrak lama.
        ts_candidate = (
            measured_at_utc
            if measured_at_utc is not None
            else msg.get("ts")
        )

        ts = self._effective_ts(
            ts_candidate,
            received_at,
            flags,
        )

        # --------------------------------------------------------
        # 5. SIMPAN KE SQLITE
        # --------------------------------------------------------

        row = (
            room_id,
            device_id,
            seq,
            to_iso(ts),
            to_iso(received_at),
            int(round(co2)) if co2 is not None else None,
            temp_in,
            hum_in,
            temp_out,
            hum_out,
            pir,
            rssi,
            json.dumps(faults),
            json.dumps(flags),
            raw,
            boot_id,
            uptime_ms,
            measured_at_utc,
        )

        try:
            self.db.execute(
                """
                INSERT INTO sensor_reading (
                    room_id,
                    device_id,
                    seq,
                    ts_utc,
                    received_at,
                    co2_ppm,
                    temp_in_c,
                    hum_in_pct,
                    temp_out_c,
                    hum_out_pct,
                    pir,
                    rssi,
                    faults,
                    quality_flags,
                    raw,
                    boot_id,
                    uptime_ms,
                    measured_at_utc
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                row,
            )

        except sqlite3.IntegrityError:
            log.info(
                "Pesan duplikat diabaikan "
                "(device=%s, boot=%s, seq=%s)",
                device_id,
                boot_id,
                seq,
            )
            return None

        # Perbarui urutan hanya setelah INSERT berhasil.
        self._check_seq(device_id, seq, boot_id)

        # --------------------------------------------------------
        # 6. PREDIKSI DAN REKOMENDASI
        # --------------------------------------------------------

        result = {
            "room_id": room_id,
            "ts": to_iso(ts),
            "flags": flags,
            "co2_ppm": co2,
        }

        if co2 is not None and "suspect" not in flags:
            result["recommendation"] = self._predict_and_recommend(
                room_id,
                to_iso(ts),
                ts,
            )

        return result

    # ============================================================
    # TIMESTAMP VALIDATION
    # ============================================================

    def _effective_ts(
        self,
        ts_raw,
        received_at: datetime,
        flags: list[str],
    ) -> datetime:
        """Tentukan waktu efektif berdasarkan toleransi timestamp."""

        try:
            ts = (
                parse_iso(ts_raw)
                if isinstance(ts_raw, str)
                else None
            )
        except (ValueError, TypeError):
            ts = None

        if (
            ts is None
            or abs(
                (ts - received_at).total_seconds()
            ) > self.s.ts_tolerance_s
        ):
            flags.append("ts_corrected")
            return received_at

        return ts

    # ============================================================
    # SEQUENCE TRACKING
    # ============================================================

    def _check_seq(
        self,
        device_id: str,
        seq: int | None,
        boot_id: str | None = None,
    ) -> None:
        """Periksa indikasi pesan hilang atau tidak berurutan."""

        if seq is None:
            return

        key = (device_id, boot_id)
        last = self._last_seq.get(key)

        if last is not None:
            if seq > last + 1:
                log.warning(
                    "Pesan berpotensi hilang dari %s "
                    "(boot=%s): seq %s -> %s",
                    device_id,
                    boot_id,
                    last,
                    seq,
                )

            elif seq <= last:
                log.warning(
                    "Pesan tidak berurutan dari %s "
                    "(boot=%s): seq=%s, last=%s",
                    device_id,
                    boot_id,
                    seq,
                    last,
                )

        if last is None or seq > last:
            self._last_seq[key] = seq

    # ============================================================
    # PREDICTION AND RECOMMENDATION
    # ============================================================

    def recent_co2(
        self,
        room_id: str,
        limit: int = HISTORY_FOR_PREDICTOR,
    ) -> list[float]:
        """Ambil pembacaan CO2 terbaru untuk predictor."""

        rows = self.db.query(
            """
            SELECT co2_ppm
            FROM sensor_reading
            WHERE room_id = ?
              AND co2_ppm IS NOT NULL
              AND quality_flags NOT LIKE '%suspect%'
            ORDER BY ts_utc DESC, id DESC
            LIMIT ?
            """,
            (room_id, limit),
        )

        return [
            float(row["co2_ppm"])
            for row in reversed(rows)
        ]

    def _predict_and_recommend(
        self,
        room_id: str,
        created_at: str,
        ts: datetime,
    ) -> dict:
        """Menjalankan prediksi dan menyimpan rekomendasi."""

        forecast = self.predictor.predict(
            self.recent_co2(room_id)
        )

        rec = recommend(forecast, self.s)

        self.db.executemany(
            """
            INSERT INTO prediction (
                room_id,
                created_at,
                target_ts,
                horizon_min,
                co2_ppm,
                model
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    room_id,
                    created_at,
                    to_iso(ts + timedelta(minutes=k)),
                    k,
                    value,
                    self.predictor.name,
                )
                for k, value in enumerate(forecast, start=1)
            ],
        )

        self.db.execute(
            """
            INSERT INTO recommendation (
                room_id,
                created_at,
                action,
                minutes,
                predicted_peak_ppm,
                predicted_at_15min_ppm,
                model
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                room_id,
                created_at,
                rec.action,
                rec.minutes,
                rec.peak,
                rec.at15,
                self.predictor.name,
            ),
        )

        recommendation_payload = {
            "v": 1,
            "ts": created_at,
            "action": rec.action,
            "minutes": rec.minutes,
            "predicted_peak_ppm": round(rec.peak),
            "predicted_at_15min_ppm": round(rec.at15),
            "model": self.predictor.name,
        }

        if self.publisher:
            try:
                self.publisher(
                    room_id,
                    recommendation_payload,
                )
            except Exception:
                # Gagal publish rekomendasi tidak membatalkan
                # penyimpanan data sensor yang sudah berhasil.
                log.exception(
                    "Gagal mengirim rekomendasi ke MQTT"
                )

        return recommendation_payload
