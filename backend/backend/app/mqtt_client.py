
"""Jembatan MQTT: menerima pesan sensor dan status, mengirim rekomendasi ke ESP32."""

from __future__ import annotations

import json
import logging
import ssl
from pathlib import Path

import paho.mqtt.client as mqtt

from .config import Settings
from .ingest import Pipeline


log = logging.getLogger("co2class.mqtt")


class MqttBridge:
    def __init__(self, settings: Settings, pipeline: Pipeline):
        self.s = settings
        self.pipeline = pipeline
        self.device_status: dict[str, str] = {}

        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="co2class-backend",
        )

        # Autentikasi MQTT
        if settings.mqtt_username:
            self._client.username_pw_set(
                settings.mqtt_username,
                settings.mqtt_password or None,
            )

        # Konfigurasi TLS untuk broker H200
        if settings.mqtt_enabled and settings.mqtt_tls_enabled:
            cert = Path(settings.mqtt_ca_cert).expanduser()

            if not cert.is_file():
                raise FileNotFoundError(
                    f"Sertifikat MQTT CA tidak ditemukan: {cert}"
                )

            self._client.tls_set(
                ca_certs=str(cert),
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )

        # MQTT callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    @property
    def connected(self) -> bool:
        return self._client.is_connected()

    def start(self) -> None:
        """
        Menjalankan koneksi MQTT secara asynchronous.

        Backend tetap berjalan ketika broker belum tersedia.
        Paho MQTT akan mencoba reconnect secara otomatis.
        """
        self._client.reconnect_delay_set(
            min_delay=1,
            max_delay=30,
        )

        self._client.connect_async(
            self.s.mqtt_host,
            self.s.mqtt_port,
            keepalive=60,
        )

        self._client.loop_start()

        log.info(
            "MQTT: mencoba tersambung ke %s:%s",
            self.s.mqtt_host,
            self.s.mqtt_port,
        )

    def stop(self) -> None:
        """Menghentikan MQTT client."""
        self._client.loop_stop()
        self._client.disconnect()

    def publish_recommendation(
        self,
        room_id: str,
        payload: dict,
    ) -> None:
        """
        Mengirim rekomendasi ventilasi melalui MQTT.

        Pesan dikirim menggunakan QoS 1 dan retain=True
        agar rekomendasi terakhir tersedia ketika perangkat
        kembali terhubung.
        """
        topic = (
            f"{self.s.mqtt_topic_prefix}/"
            f"{room_id}/recommendation"
        )

        self._client.publish(
            topic,
            json.dumps(payload),
            qos=1,
            retain=True,
        )

    # ============================================================
    # MQTT CALLBACKS
    # ============================================================

    def _on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties=None,
    ):
        """Dipanggil ketika MQTT client berhasil/gagal connect."""

        if reason_code != 0:
            log.error(
                "MQTT gagal tersambung: %s",
                reason_code,
            )
            return

        prefix = self.s.mqtt_topic_prefix

        topics = [
            (self.s.mqtt_sensor_topic, 1),
            (f"{prefix}/+/status", 1),
        ]

        client.subscribe(topics)

        log.info(
            "MQTT tersambung, subscribe %s",
            topics,
        )

    def _on_disconnect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties=None,
    ):
        """Dipanggil ketika koneksi MQTT terputus."""

        log.warning(
            "MQTT terputus (%s), akan mencoba lagi",
            reason_code,
        )

    def _on_message(self, client, userdata, msg):
        """
        Memproses pesan MQTT berdasarkan topiknya.

        Mendukung:
        1. classroom/gd525/sensors
        2. classroom/gd525/status
        3. co2class/gd525/sensor (legacy)
        4. co2class/gd525/status (legacy)
        """

        try:
            topic = msg.topic

            # ====================================================
            # 1. DATA SENSOR ESP32 AKTUAL
            # ====================================================

            if topic == self.s.mqtt_sensor_topic:

                log.info(
                    "MQTT menerima data: %s",
                    msg.payload.decode("utf-8", "replace"),
                )

                result = self.pipeline.handle_sensor_message(
                    self.s.room_id,
                    msg.payload,
                )

                if result is not None:
                    log.info(
                        "Data berhasil diproses: CO2=%s ppm | flags=%s",
                        result["co2_ppm"],
                        result["flags"],
                    )
                else:
                    log.warning(
                        "Data MQTT tidak berhasil diproses"
                    )

                return

            # ====================================================
            # 2. PARSING TOPIK MQTT
            # ====================================================

            parts = topic.split("/")

            if len(parts) != 3:
                log.debug(
                    "Topik MQTT diabaikan: %s",
                    topic,
                )
                return

            prefix, room_id, kind = parts

            # ====================================================
            # 3. DATA SENSOR LEGACY
            # ====================================================

            if prefix == "co2class" and kind == "sensor":

                result = self.pipeline.handle_sensor_message(
                    room_id,
                    msg.payload,
                )

                if result is not None:
                    log.info(
                        "Data sensor legacy berhasil diproses "
                        "untuk ruangan %s",
                        room_id,
                    )
                else:
                    log.warning(
                        "Data sensor legacy gagal diproses "
                        "untuk ruangan %s",
                        room_id,
                    )

                return

            # ====================================================
            # 4. STATUS PERANGKAT
            # ====================================================

            if (
                prefix in (
                    self.s.mqtt_topic_prefix,
                    "co2class",
                )
                and kind == "status"
            ):

                status = msg.payload.decode(
                    "utf-8",
                    "replace",
                ).strip()

                self.device_status[room_id] = status

                log.info(
                    "Status perangkat %s: %s",
                    room_id,
                    status,
                )

                return

            # ====================================================
            # 5. TOPIK TIDAK DIKENALI
            # ====================================================

            log.debug(
                "Topik MQTT tidak dikenali: %s",
                topic,
            )

        except Exception:
            log.exception(
                "Gagal memproses pesan MQTT di topik %s",
                msg.topic,
            )
