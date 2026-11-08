
#!/usr/bin/env python3
"""Windows MQTT relay: local broker -> SQLite queue -> H200 via SSH.

Supported payloads:
- ESP32 legacy V4.2: co2, temperature, humidity, pir
- ESP32 V4.3: device_id, boot_id, seq, uptime_ms,
  measured_at_utc, co2_ppm, temp_in_c, hum_in_pct, pir

Notes:
- Delivery is at-least-once after local queue acceptance.
- A lost remote ACK can cause duplicate forwarding.
- ESP32 QoS0 messages can be lost before local acceptance.
"""

import argparse
import getpass
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import threading
import time

from pathlib import Path


TOPIC = "classroom/gd525/sensors"

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


def init_db(path):
    """Initialize persistent local forwarding queue."""

    conn = sqlite3.connect(
        path,
        timeout=15,
        check_same_thread=False,
    )

    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            payload TEXT NOT NULL,
            queued_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    return conn


def valid_payload(payload):
    """Accept legacy and V4.3 sensor JSON payloads."""

    if len(payload) > 4096:
        return False

    try:
        data = json.loads(payload.decode("utf-8"))

        if not isinstance(data, dict):
            return False

        keys = set(data)

        # Backward compatibility: ESP32 V4.2.
        if LEGACY_FIELDS.issubset(keys):
            return True

        # ESP32 V4.3.
        if V43_FIELDS.issubset(keys):
            device_id = data.get("device_id")
            boot_id = data.get("boot_id")
            seq = data.get("seq")
            uptime_ms = data.get("uptime_ms")

            if not isinstance(device_id, str) or not device_id.strip():
                return False

            if not isinstance(boot_id, str) or not boot_id.strip():
                return False

            if type(seq) is not int or seq < 0:
                return False

            if type(uptime_ms) is not int or uptime_ms < 0:
                return False

            return True

        return False

    except (ValueError, UnicodeDecodeError, TypeError):
        return False


def forward_once(conn, ssh_target, remote_cmd):
    """Forward queued rows and remove only after remote ACK."""

    cmd = [
        "ssh",
        "-T",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=2",
        ssh_target,
        remote_cmd,
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1,
    )

    try:
        while proc.poll() is None:
            row = conn.execute(
                """
                SELECT id, topic, payload
                FROM pending
                ORDER BY id
                LIMIT 1
                """
            ).fetchone()

            if row is None:
                time.sleep(1)
                continue

            msg_id, topic, payload = row

            proc.stdin.write(
                json.dumps({
                    "id": msg_id,
                    "topic": topic,
                    "payload": payload,
                }) + "\n"
            )

            proc.stdin.flush()

            ack_line = proc.stdout.readline()

            if not ack_line:
                raise RuntimeError(
                    "SSH ended before remote acknowledgement"
                )

            ack = json.loads(ack_line)

            if (
                ack.get("id") != msg_id
                or ack.get("ok") is not True
            ):
                raise RuntimeError(
                    "Bad remote acknowledgement"
                )

            conn.execute(
                "DELETE FROM pending WHERE id=?",
                (msg_id,),
            )
            conn.commit()

            print(
                f"[FORWARDED] #{msg_id}: {payload[:100]}",
                flush=True,
            )

    finally:
        if proc.poll() is None:
            proc.terminate()

        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main():
    try:
        import paho.mqtt.client as mqtt

    except ImportError:
        print(
            'Install dependency: py -m pip install "paho-mqtt>=2,<3"',
            file=sys.stderr,
        )
        raise SystemExit(2)

    parser = argparse.ArgumentParser(
        description="GD525 local MQTT to H200 SSH relay"
    )

    parser.add_argument(
        "--ssh-target",
        required=True,
        help="Tailscale SSH alias, e.g. bryan@100.x.y.z",
    )

    parser.add_argument(
        "--local-host",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--local-port",
        type=int,
        default=1883,
    )

    parser.add_argument(
        "--local-user",
        default="gd525_dev",
    )

    parser.add_argument(
        "--db",
        default=str(
            Path(__file__).with_name("relay_queue.sqlite3")
        ),
    )

    parser.add_argument(
        "--remote-root",
        default="/home/bryan/co2-classroom-iot",
    )

    args = parser.parse_args()

    password = (
        os.environ.get("GD525_LOCAL_MQTT_PASSWORD")
        or getpass.getpass("Local broker password: ")
    )

    db_path = Path(args.db).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    writer = init_db(db_path)
    reader = init_db(db_path)

    lock = threading.Lock()

    def on_connect(
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        if reason_code != 0:
            print(
                f"[MQTT] failed to connect: {reason_code}",
                file=sys.stderr,
            )
            return

        client.subscribe(TOPIC, qos=1)

        print(
            "[MQTT] Listening on local topic:",
            TOPIC,
            flush=True,
        )

    def on_message(client, userdata, msg):
        if not valid_payload(msg.payload):
            print(
                "[REJECTED] invalid sensor payload",
                file=sys.stderr,
                flush=True,
            )
            return

        with lock:
            writer.execute(
                """
                INSERT INTO pending(topic, payload)
                VALUES (?, ?)
                """,
                (
                    msg.topic,
                    msg.payload.decode("utf-8"),
                ),
            )

            writer.commit()

            count = writer.execute(
                "SELECT COUNT(*) FROM pending"
            ).fetchone()[0]

        print(
            f"[QUEUED] pending={count}",
            flush=True,
        )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="gd525-dev-relay-win",
    )

    client.username_pw_set(
        args.local_user,
        password,
    )

    client.on_connect = on_connect
    client.on_message = on_message

    client.reconnect_delay_set(
        min_delay=1,
        max_delay=30,
    )

    client.connect(
        args.local_host,
        args.local_port,
        45,
    )

    client.loop_start()

    root = shlex.quote(args.remote_root)

    remote_cmd = (
        f"cd {root} && "
        "backend/backend/.venv/bin/python "
        "deployment/dev-gateway/remote_sink.py"
    )

    print(
        f"[SSH] forwarding to {args.ssh_target} "
        "(verify known_hosts first)",
        flush=True,
    )

    try:
        while True:
            try:
                forward_once(
                    reader,
                    args.ssh_target,
                    remote_cmd,
                )

            except (
                OSError,
                ValueError,
                RuntimeError,
                subprocess.SubprocessError,
            ) as exc:
                print(
                    f"[SSH] offline/retry: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

                time.sleep(5)

    except KeyboardInterrupt:
        print("\nStopping relay.")

    finally:
        client.loop_stop()
        client.disconnect()

        writer.close()
        reader.close()


if __name__ == "__main__":
    main()
