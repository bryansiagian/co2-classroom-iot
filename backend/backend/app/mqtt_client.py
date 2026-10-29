"""Jembatan MQTT: menerima pesan sensor dan status, mengirim rekomendasi ke ESP32."""
from __future__ import annotations

import json
import logging

import paho.mqtt.client as mqtt

from .config import Settings
from .ingest import Pipeline

log = logging.getLogger("co2class.mqtt")


class MqttBridge:
    def __init__(self, settings: Settings, pipeline: Pipeline):
        self.s = settings
        self.pipeline = pipeline
        self.device_status: dict[str, str] = {}
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="co2class-backend")
        if settings.mqtt_username:
            self._client.username_pw_set(settings.mqtt_username, settings.mqtt_password or None)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    @property
    def connected(self) -> bool:
        return self._client.is_connected()

    def start(self) -> None:
        # connect_async + loop_start: backend tetap hidup walau broker belum menyala, lalu tersambung otomatis.
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.connect_async(self.s.mqtt_host, self.s.mqtt_port, keepalive=60)
        self._client.loop_start()
        log.info("MQTT: mencoba tersambung ke %s:%s", self.s.mqtt_host, self.s.mqtt_port)

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish_recommendation(self, room_id: str, payload: dict) -> None:
        topic = f"{self.s.mqtt_topic_prefix}/{room_id}/recommendation"
        self._client.publish(topic, json.dumps(payload), qos=1, retain=True)

    # ---------------------------------------------------------------- callbacks
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            log.error("MQTT gagal tersambung: %s", reason_code)
            return
        p = self.s.mqtt_topic_prefix
        client.subscribe([(f"{p}/+/sensor", 1), (f"{p}/+/status", 1)])
        log.info("MQTT tersambung, subscribe %s/+/sensor dan %s/+/status", p, p)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        log.warning("MQTT terputus (%s), akan mencoba lagi", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            parts = msg.topic.split("/")
            if len(parts) != 3:
                return
            _, room_id, kind = parts
            if kind == "sensor":
                self.pipeline.handle_sensor_message(room_id, msg.payload)
            elif kind == "status":
                self.device_status[room_id] = msg.payload.decode("utf-8", "replace").strip()
                log.info("Status perangkat %s: %s", room_id, self.device_status[room_id])
        except Exception:
            log.exception("Gagal memproses pesan MQTT di topik %s", msg.topic)
