import os
import ssl
import json
import time
import sqlite3
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# ==================================
# KONFIGURASI
# ==================================

MQTT_HOST = "172.22.44.29"
MQTT_PORT = 8883

MQTT_USER = "backend_gd525"
MQTT_PASSWORD = os.environ["MQTT_PASSWORD"]

MQTT_TOPIC = "classroom/gd525/sensors"

CA_CERT = "/etc/mosquitto/certs/server.crt"

DB_PATH = "gd525_test.db"

DURATION_SECONDS = 15 * 60

# ==================================
# DATABASE
# ==================================

conn = sqlite3.connect(DB_PATH)

conn.execute("""
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at_utc TEXT NOT NULL,
    co2 INTEGER NOT NULL,
    temperature REAL NOT NULL,
    humidity REAL NOT NULL,
    pir INTEGER NOT NULL
)
""")

conn.commit()

# ==================================
# CALLBACK MQTT
# ==================================

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("MQTT TERHUBUNG!", flush=True)

        client.subscribe(MQTT_TOPIC, qos=0)
        print(f"Subscribe: {MQTT_TOPIC}", flush=True)
    else:
        print(f"MQTT gagal: {reason_code}", flush=True)


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))

        co2 = int(data["co2"])
        temperature = float(data["temperature"])
        humidity = float(data["humidity"])
        pir = int(data["pir"])

        if not (
            0 <= co2 <= 10000
            and -40 <= temperature <= 80
            and 0 <= humidity <= 100
            and pir in (0, 1)
        ):
            raise ValueError("Nilai sensor di luar batas validasi")

        timestamp = datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds")

        conn.execute("""
            INSERT INTO sensor_readings (
                received_at_utc,
                co2,
                temperature,
                humidity,
                pir
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            timestamp,
            co2,
            temperature,
            humidity,
            pir
        ))

        conn.commit()

        print(
            f"[{timestamp}] "
            f"CO2={co2} ppm | "
            f"T={temperature} C | "
            f"RH={humidity}% | "
            f"PIR={pir}",
            flush=True
        )

    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"Data tidak valid: {error}", flush=True)


# ==================================
# MQTT CLIENT
# ==================================

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="backend-gd525-test",
    protocol=mqtt.MQTTv311
)

client.username_pw_set(
    MQTT_USER,
    MQTT_PASSWORD
)

client.tls_set(
    ca_certs=CA_CERT,
    cert_reqs=ssl.CERT_REQUIRED,
    tls_version=ssl.PROTOCOL_TLS_CLIENT
)

client.on_connect = on_connect
client.on_message = on_message

# ==================================
# MAIN
# ==================================

try:
    print("=== GD525 COLLECTOR ===")
    print("Durasi penyimpanan: 15 menit")

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)

    start = time.monotonic()

    while time.monotonic() - start < DURATION_SECONDS:
        client.loop(timeout=1.0)

except KeyboardInterrupt:
    print("\nDihentikan manual.")

finally:
    client.disconnect()

    total = conn.execute(
        "SELECT COUNT(*) FROM sensor_readings"
    ).fetchone()[0]

    conn.close()

    print("\n=== PENGUMPULAN SELESAI ===")
    print(f"Total baris dalam database: {total}")
    print(f"Database: {DB_PATH}")
