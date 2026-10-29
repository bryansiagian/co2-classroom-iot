from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def iso_to_ms(s: str) -> int:
    return int(parse_iso(s).timestamp() * 1000)


def ms_to_iso(ms: int) -> str:
    return to_iso(datetime.fromtimestamp(ms / 1000, tz=timezone.utc))
