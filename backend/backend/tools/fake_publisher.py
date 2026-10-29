"""Mengirim data sensor simulasi ke MQTT, meniru ESP32 sebelum alat tersedia.

Jalankan dari folder backend/:
    python -m tools.fake_publisher                 # 1 pesan per menit
    python -m tools.fake_publisher --interval 5    # lebih cepat untuk uji
Data ini simulasi, jangan dipakai sebagai data TA.
"""
import argparse
import json
import time

import paho.mqtt.client as mqtt

from app.config import settings
from app.timeutil import to_iso, utcnow

from .scenario import sensor_message


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=settings.mqtt_host)
    ap.add_argument("--port", type=int, default=settings.mqtt_port)
    ap.add_argument("--room", default=settings.room_id)
    ap.add_argument("--device", default="esp32-gd525-01")
    ap.add_argument("--interval", type=float, default=60, help="detik antar pesan")
    ap.add_argument("--count", type=int, default=0, help="0 = tanpa batas")
    args = ap.parse_args()

    topic = f"{settings.mqtt_topic_prefix}/{args.room}/sensor"
    status_topic = f"{settings.mqtt_topic_prefix}/{args.room}/status"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"fake-{args.device}")
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password or None)
    client.will_set(status_topic, "offline", qos=1, retain=True)
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    client.publish(status_topic, "online", qos=1, retain=True)
    print(f"Mengirim ke {args.host}:{args.port} topik {topic} tiap {args.interval}s (Ctrl+C untuk berhenti)")

    seq = 0
    try:
        while args.count == 0 or seq < args.count:
            now = utcnow()
            msg = sensor_message(int(now.timestamp() // 60), to_iso(now), seq, args.device)
            client.publish(topic, json.dumps(msg), qos=1)
            print(f"seq={seq} co2={msg['co2_ppm']} ppm pir={msg['pir']}")
            seq += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(status_topic, "offline", qos=1, retain=True).wait_for_publish(timeout=3)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
