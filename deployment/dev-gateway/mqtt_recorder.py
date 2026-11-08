
#!/usr/bin/env python3
"""Record complete GD525 MQTT sensor payloads into JSONL.

Each line contains:
- received_at_utc: Windows subscriber receipt time
- topic: MQTT topic
- qos: MQTT quality of service
- payload: original decoded sensor JSON
"""

import argparse
import getpass
import json
import os
import sys

from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt


TOPIC = "classroom/gd525/sensors"


def utc_now():
    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--host",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=1883,
    )

    parser.add_argument(
        "--user",
        default="gd525_dev",
    )

    parser.add_argument(
        "--output",
        default="mqtt_v43_capture.jsonl",
    )

    args = parser.parse_args()

    password = (
        os.environ.get("GD525_LOCAL_MQTT_PASSWORD")
        or getpass.getpass("Local MQTT password: ")
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    count = 0

    def on_connect(
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        if reason_code == 0:
            client.subscribe(TOPIC, qos=1)
            print(f"[CONNECTED] Subscribed: {TOPIC}", flush=True)
        else:
            print(f"[ERROR] MQTT connect: {reason_code}", flush=True)

    def on_message(client, userdata, msg):
        nonlocal count

        try:
            payload = json.loads(
                msg.payload.decode("utf-8")
            )
        except (ValueError, UnicodeDecodeError):
            print("[WARNING] Invalid JSON received", flush=True)
            payload = {
                "_raw": msg.payload.decode(
                    "utf-8",
                    errors="replace",
                )
            }

        record = {
            "received_at_utc": utc_now(),
            "topic": msg.topic,
            "qos": msg.qos,
            "payload": payload,
        }

        with output.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

        count += 1

        seq = (
            payload.get("seq")
            if isinstance(payload, dict)
            else None
        )

        boot_id = (
            payload.get("boot_id")
            if isinstance(payload, dict)
            else None
        )

        print(
            f"[CAPTURED] count={count} "
            f"boot={boot_id} seq={seq}",
            flush=True,
        )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="gd525-mqtt-recorder",
    )

    client.username_pw_set(
        args.user,
        password,
    )

    client.on_connect = on_connect
    client.on_message = on_message

    client.reconnect_delay_set(
        min_delay=1,
        max_delay=30,
    )

    print(f"[OUTPUT] {output.resolve()}")

    try:
        client.connect(
            args.host,
            args.port,
            keepalive=45,
        )

        client.loop_forever()

    except KeyboardInterrupt:
        print(f"\n[STOPPED] Total captured: {count}")

    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
