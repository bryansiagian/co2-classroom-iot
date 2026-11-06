# GD525 Sensor V4.2: dual-mode Wi-Fi and MQTT

Firmware adapted from V4.1; DHT22 GPIO4, PIR GPIO27, MH-Z19C RX26/TX25, publish every 10s with same `co2`, `temperature`, `humidity`, `pir` JSON.

## Arduino IDE
1. Make folder `GD525_Sensor_V4_2` and put `GD525_Sensor_V4_2.ino` inside it. Copy `secrets.h.example` to `secrets.h` **inside the same folder**.
2. Replace placeholders in `secrets.h` locally. `DEV_MQTT_HOST` is **Windows Mobile Hotspot adapter IPv4** (obtain from `ipconfig`); not the Tailscale IP, not 127.0.0.1, not the ESP32 address.
3. Enable `GD525-DEV` hotspot 2.4 GHz, Mosquitto local on 1883, Python relay to H200. Windows Firewall must allow ESP32 access on 1883 from hotspot private network only.
4. Select ESP32 Dev Module and correct COM port. Upload. Serial Monitor 115200 baud. DEV is attempted first for up to 12 s, otherwise HW-Mahasiswa for up to 12 s; after loss, both retried.
5. Expect `[MODE] DEV`, `[MQTT] TERHUBUNG!` and `[MQTT] Publish berhasil`. Check CMD relay `[FORWARDED]`, then H200 SQLite last sensor rows.

## Caveats
- DEV MQTT to laptop is plaintext within a trusted hotspot; **never expose port 1883 to internet**.
- Campus H200 connection remains TLS with the previously supplied certificate; do not use TLS setInsecure().
- Campus mode uses NTP or compilation-time WIB fallback. Build-time fallback is NOT a reliable real-time clock after long power-off. The backend continues using UTC `received_at`.
- Credentials are examples only; rotate the previously exposed local MQTT password. Keep `secrets.h` out of Git.
- All data collected off-campus is development data, not official GD525 research data.
- This code has not been compiled with your specific Arduino-ESP32 libraries or flashed to your hardware yet; verify compile and Serial Monitor before considering it deployed.
