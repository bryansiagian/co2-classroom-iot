
#!/usr/bin/env python3
"""H200 remote sink: receive JSON lines via SSH and forward to MQTT TLS.

Supported sensor payloads:
- Legacy ESP32 V4.2:
  co2, temperature, humidity, pir

- ESP32 V4.3:
  device_id, boot_id, seq, uptime_ms,
  measured_at_utc, co2_ppm, temp_in_c, hum_in_pct, pir

Delivery:
- Messages are published to the H200 MQTT broker using QoS 1.
- ACK is returned to Windows only after MQTT publish confirmation.
- Missing ACK causes the Windows SQLite queue to retry.
- Duplicate delivery is possible; backend deduplication handles V4.3
  messages with the same device_id, boot_id, and seq.
"""

import json
import os
import sys

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

TOPIC = "classroom/gd525/sensors"

MAX_PAYLOAD_BYTES = 4096

LEGACY_FIELDS = {
    "co2",
    "temperature",
    "humidity",
    "pir",
}

V43_FIELDS = {
    "device_id",
    "boot_id",
    "seq",
    "uptime_ms",
    "measured_at_utc",
    "co2_ppm",
    "temp_in_c",
    "hum_in_pct",
    "pir",
}


# ============================================================
# MQTT BROKER CONFIGURATION
# ============================================================

def broker_config():
    """Read MQTT configuration from environment variables."""

    username = (
        os.environ.get("MQTT_USERNAME")
        or os.environ.get("MQTT_USER")
    )

    password = os.environ.get("MQTT_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            "MQTT_USERNAME and MQTT_PASSWORD must be "
            "defined in backend/.env or environment"
        )

    ca_path = (
        ROOT
        / "backend"
        / "backend"
        / os.environ.get(
            "MQTT_CA_CERT",
            "certs/server.crt",
        )
    )

    return {
        "host": os.environ.get(
            "MQTT_HOST",
            "172.22.44.29",
        ),
        "port": int(
            os.environ.get("MQTT_PORT", "8883")
        ),
        "username": username,
        "password": password,
        "ca": ca_path,
    }


# ============================================================
# PAYLOAD VALIDATION
# ============================================================

def validate_sensor_payload(doc):
    """Validate legacy or V4.3 sensor payload structure."""

    if not isinstance(doc, dict):
        raise ValueError("invalid sensor JSON")

    keys = set(doc)

    # --------------------------------------------------------
    # ESP32 V4.2 / LEGACY
    # --------------------------------------------------------

    if LEGACY_FIELDS.issubset(keys):
        return "legacy"

    # --------------------------------------------------------
    # ESP32 V4.3
    # --------------------------------------------------------

    if V43_FIELDS.issubset(keys):
        device_id = doc.get("device_id")
        boot_id = doc.get("boot_id")
        seq = doc.get("seq")
        uptime_ms = doc.get("uptime_ms")

        if (
            not isinstance(device_id, str)
            or not device_id.strip()
        ):
            raise ValueError("invalid device_id")

        if (
            not isinstance(boot_id, str)
            or not boot_id.strip()
        ):
            raise ValueError("invalid boot_id")

        if type(seq) is not int or seq < 0:
            raise ValueError("invalid seq")

        if type(uptime_ms) is not int or uptime_ms < 0:
            raise ValueError("invalid uptime_ms")

        return "v4.3"

    raise ValueError(
        "unsupported sensor payload: "
        "expected legacy or V4.3 fields"
    )


def validate(msg):
    """Validate SSH message envelope and sensor payload."""

    if not isinstance(msg, dict):
        raise ValueError("invalid message envelope")

    msg_id = msg.get("id")

    if type(msg_id) is not int or msg_id <= 0:
        raise ValueError("invalid id")

    if msg.get("topic") != TOPIC:
        raise ValueError("forbidden topic")

    payload = msg.get("payload")

    if not isinstance(payload, str):
        raise ValueError("invalid payload")

    if (
        not payload
        or len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES
    ):
        raise ValueError("invalid payload size")

    try:
        doc = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "invalid sensor JSON"
        ) from exc

    validate_sensor_payload(doc)

    # Forward the original payload without changing fields.
    return msg_id, payload


# ============================================================
# REMOTE SINK
# ============================================================

def main():
    try:
        from dotenv import load_dotenv
        import paho.mqtt.client as mqtt

    except ImportError as exc:
        sys.stderr.write(
            f"Missing dependency in H200 backend venv: {exc}\n"
        )
        raise SystemExit(2)

    # Existing configuration behavior is preserved.
    load_dotenv(
        ROOT / "backend" / ".env",
        override=False,
    )

    load_dotenv(
        ROOT
        / "deployment"
        / "dev-gateway"
        / ".env.gateway",
        override=True,
    )

    cfg = broker_config()

    if not cfg["ca"].is_file():
        raise RuntimeError(
            f'TLS CA file not found: {cfg["ca"]}'
        )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"gd525-dev-relay-{os.getpid()}",
    )

    client.username_pw_set(
        cfg["username"],
        cfg["password"],
    )

    client.tls_set(
        ca_certs=str(cfg["ca"])
    )

    client.connect(
        cfg["host"],
        cfg["port"],
        keepalive=45,
    )

    client.loop_start()

    try:
        for line in sys.stdin:
            try:
                message = json.loads(line)

                msg_id, payload = validate(message)

                result = client.publish(
                    TOPIC,
                    payload,
                    qos=1,
                    retain=False,
                )

                result.wait_for_publish(timeout=15)

                if (
                    not result.is_published()
                    or result.rc != mqtt.MQTT_ERR_SUCCESS
                ):
                    raise RuntimeError(
                        f"MQTT publish failed: {result.rc}"
                    )

                # ACK is sent only after broker confirmation.
                print(
                    json.dumps({
                        "id": msg_id,
                        "ok": True,
                    }),
                    flush=True,
                )

            except Exception as exc:
                sys.stderr.write(
                    "Remote sink error: "
                    f"{type(exc).__name__}: {exc}\n"
                )

                # Do not ACK.
                # Windows relay will retry queued messages.
                raise SystemExit(3)

    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
