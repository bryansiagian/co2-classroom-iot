# GD525 remote development gateway

Panduan lengkap: [docs/development-outside-campus.md](../../docs/development-outside-campus.md)

- `local_relay.py`: broker lokal -> antrean SQLite -> SSH/Tailscale.
- `remote_sink.py`: SSH stdin -> broker H200 MQTT TLS (existing credentials from backend/.env).
- `mosquitto-dev.conf.example`: konfigurasi Mosquitto laptop dengan authentication.
- `tests/test_gateway.py`: validasi payload dan persistensi antrean.

Penting: tidak mengubah listener H200, backend FastAPI, atau firmware sensor yang ada. Contoh firmware **perlu diintegrasikan ke sketch asli**, bukan di-flash langsung.
