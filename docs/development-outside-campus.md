# Pengembangan ESP32 GD525 di luar kampus (hotspot + Tailscale SSH)

> Status: rancangan siap diuji; **belum dibuktikan end-to-end dengan ESP32/H200 milik tim**. Mode ini untuk data development, **bukan** dataset resmi ruang GD525.

## Arsitektur

ESP32 --(Wi-Fi `GD525-DEV`, MQTT 1883 + username/password)--> broker Mosquitto **lokal di laptop** --> `local_relay.py` + antrean SQLite --> SSH ke H200 melalui Tailscale --> `remote_sink.py` di H200 --> Mosquitto H200 (`172.22.44.29:8883`, TLS) --> FastAPI existing --> SQLite existing.

Broker H200 tidak diekspos ke internet. Di kampus: ESP32 kembali menggunakan `HW-Mahasiswa` + TLS langsung ke H200 (firmware V4.1). **Jangan** ganti backend systemd atau listener produksi H200.

## Prasyarat

- Laptop Windows tersambung ke Internet dan Tailscale; SSH `bryan@100.x.y.z` sudah dapat dilakukan. Gunakan IP Tailscale aktual, jangan menyalin contoh.
- Hotspot Windows diaktifkan, nama `GD525-DEV`, band 2.4 GHz; pastikan ESP32 mendapatkan IP.
- Mosquitto untuk Windows terinstal; jika belum: https://mosquitto.org/download/ (gunakan instalasi resmi).
- Python 3.x Windows; `py -m pip install "paho-mqtt>=2,<3"`.
- H200: `backend/backend/.venv/bin/python` memiliki `paho-mqtt`, `python-dotenv`; file `backend/.env` berisi `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME` (atau `MQTT_USER`), `MQTT_PASSWORD`, `MQTT_CA_CERT` jika berbeda dari `certs/server.crt`.
- Pada H200: `sudo systemctl is-active mosquitto` dan `sudo systemctl is-active co2class-backend` -> active.

## A. Setup laptop (sekali saja)

1. Aktifkan **Settings > Network & Internet > Mobile hotspot**, pilih **2.4 GHz** bila tersedia. Atur nama hotspot `GD525-DEV`, dengan password WPA2 yang kuat. Hubungkan ESP32 nanti ke hotspot ini.
2. Buka terminal PowerShell di **root repository** `co2-classroom-iot`.
3. Buat file password Mosquitto. Sesuaikan path ke lokasi instalasi program (contoh):

   ```powershell
   & 'C:\Program Files\mosquitto\mosquitto_passwd.exe' -c 'deployment\dev-gateway\local-passwords' gd525_dev
   ```

   Isi password **berbeda** dari password broker kampus. Jangan commit `local-passwords`.
4. Salin konfigurasi contoh, ganti `password_file` dengan **absolute path** memakai `/`. Misalnya:

   ```powershell
   Copy-Item deployment\dev-gateway\mosquitto-dev.conf.example deployment\dev-gateway\mosquitto-dev.conf
   notepad deployment\dev-gateway\mosquitto-dev.conf
   ```

   Contoh: `password_file C:/Users/WIN11/Documents/GitHub/co2-classroom-iot/deployment/dev-gateway/local-passwords`
5. Pastikan port 1883 belum dipakai service Mosquitto lain. Jalankan broker dalam satu PowerShell (biarkan terbuka):

   ```powershell
   & 'C:\Program Files\mosquitto\mosquitto.exe' -c 'deployment\dev-gateway\mosquitto-dev.conf' -v
   ```

   Jika muncul `Address already in use`, hentikan instance lama dulu atau sesuaikan port di broker, relay, dan firmware.
6. Pastikan Windows Firewall mengizinkan TCP **1883 hanya pada profil Private** untuk hotspot. Sebaiknya batasi sumber ke subnet hotspot dan **jangan** membuka port pada profil Public/Internet. Ketika laptop berpindah jaringan, hentikan broker lokal. Hotspot Windows tidak selalu dipetakan sebagai Private: periksa aturan secara spesifik.
7. Pastikan path jaringan hotspot laptop dengan `ipconfig`. Sering `192.168.137.1`, tetapi **jangan diasumsikan**.
8. Uji publish/sub lokal dari laptop, dua terminal:

   ```powershell
   & 'C:\Program Files\mosquitto\mosquitto_sub.exe' -h 127.0.0.1 -p 1883 -u gd525_dev -P '<PASSWORD_LOKAL>' -t 'classroom/gd525/sensors' -v
   & 'C:\Program Files\mosquitto\mosquitto_pub.exe' -h 127.0.0.1 -p 1883 -u gd525_dev -P '<PASSWORD_LOKAL>' -t 'classroom/gd525/sensors' -m '{"co2":700,"temperature":27,"humidity":70,"pir":0}'
   ```

   Hindari password plaintext pada riwayat terminal selama penggunaan nyata; contoh ini sekadar smoke test. Jika khawatir, gunakan `mosquitto_pub` prompt `-P` sesuai versi CLI atau uji dari ESP32 saja.

## B. Setup H200

SSH sekali via alamat Tailscale, pastikan fingerprint host benar (jangan matikan StrictHostKeyChecking). Contoh:

```powershell
ssh bryan@100.x.y.z
```

Di H200:

```bash
cd ~/co2-classroom-iot
git pull --ff-only origin main
backend/backend/.venv/bin/python -c 'import paho.mqtt.client, dotenv; print("dependency OK")'
sudo systemctl is-active mosquitto
sudo systemctl is-active co2class-backend
```

**Tes remote sink** secara langsung dari SSH (hanya setelah `.env` dan TLS cert dipastikan benar):

```bash
printf '%s\n' '{"id":1,"topic":"classroom/gd525/sensors","payload":"{\"co2\":700,\"temperature\":27,\"humidity\":70,\"pir\":0}"}' | backend/backend/.venv/bin/python deployment/dev-gateway/remote_sink.py
```

Output `{"id":1,"ok":true}` menandakan broker H200 mengakui publish (QoS 1); data percobaan **masuk ke DB development** jika FastAPI aktif. Jangan gunakan data sintetis tersebut sebagai data penelitian. Lewati tes injeksi ini jika ingin database bebas data palsu.

## C. Jalankan relay di Windows

Tes dulu akses SSH noninteraktif (gunakan SSH key):

```powershell
ssh -o BatchMode=yes bryan@100.x.y.z 'echo SSH_OK'
```

Jika gagal karena meminta password, konfigurasi SSH key melalui `ssh-keygen` dan `ssh-copy-id`/`authorized_keys` di H200 terlebih dahulu; jangan menyimpan password server dalam script.

PowerShell baru di root repository:

```powershell
py -m pip install 'paho-mqtt>=2,<3'
py deployment\dev-gateway\local_relay.py --ssh-target bryan@100.x.y.z
```

Saat ditanya `Local broker password`, masukkan password `gd525_dev`. Biarkan PowerShell relay hidup selama development; setelah relay restart, SQLite queue akan diproses kembali.

## D. Firmware ESP32

`firmware/examples/wifi_mqtt_modes_example.h` adalah **contoh adaptasi**, bukan file siap flash. Jangan menghapus firmware V4.1 yang sudah berhasil. Integrasikan hanya bagian koneksi Wi-Fi / pemilihan broker ke sketch asli, karena nama variabel TLS dan MQTT mungkin berbeda.

Dalam `secrets.h` yang sudah di-ignore Git, tambahkan:

```cpp
#define DEV_WIFI_SSID "GD525-DEV"
#define DEV_WIFI_PASSWORD "PASSWORD_HOTSPOT_LAPTOP"
#define DEV_MQTT_HOST "192.168.137.1" // gunakan IP hasil ipconfig
#define DEV_MQTT_USER "gd525_dev"
#define DEV_MQTT_PASSWORD "PASSWORD_MQTT_LOKAL"
```

Mode kampus: TLS 8883, CA cert, timestamp valid, username/password broker kampus tetap seperti firmware V4.1. Mode development: plaintext MQTT 1883 di hotspot privat dengan autentikasi berbeda. Payload & topic tetap sama. Pastikan `WiFiMulti.run()` dipanggil periodik dan broker dipilih ulang jika SSID berubah.

**Hindari** `WiFiClientSecure.setInsecure()` untuk koneksi H200. Keterbatasan NTP/fallback sertifikat kampus masih perlu penanganan tersendiri.

## E. Verifikasi end-to-end

1. Laptop menjalankan broker lokal (terminal A) dan relay (terminal B).
2. ESP32 mendapat SSID `GD525-DEV`, IP hotspot, dan `MQTT connected` pada Serial Monitor.
3. Terminal relay menampilkan `[QUEUED]` lalu `[FORWARDED]` setiap ~10 detik.
4. Di H200, amati `sudo journalctl -u co2class-backend -f` dan perubahan `sensor_reading` menggunakan query yang sudah kita pakai sebelumnya.
5. Jika ingin menguji antrean: matikan Tailscale laptop selama 30 detik (ESP32 tetap publish ke broker lokal), nyalakan lagi, pastikan `[FORWARDED]` mengejar backlog. Data yang belum diterima broker lokal selama putus koneksi Wi-Fi tidak dapat dipulihkan.

## Masalah yang mungkin terjadi

- **No Wi-Fi:** hotspot tidak 2.4 GHz, SSID/password salah, AP Windows memutus perangkat.
- **No local MQTT:** port/firewall/konfigurasi password broker lokal salah.
- **SSH returns 255:** Tailscale offline, SSH key belum dibuat, user/host salah, host key mismatch.
- **Missing remote dependency:** aktifkan `.venv` backend H200, pasang hanya dependency yang hilang sesuai `backend/backend/requirements.txt`; jangan mengubah produksi tanpa kebutuhan.
- **Remote TLS fails:** periksa nilai `MQTT_HOST`, `MQTT_PORT`, CA cert dalam `backend/.env`, waktu H200, dan status Mosquitto.
- **Queue grows:** SSH gagal, server menolak MQTT, atau remote sink gagal membaca `.env`; lihat pesan error di PowerShell relay.
- **Duplikasi:** SSH disconnect setelah publish berhasil tetapi sebelum ACK diterima dapat mengirim ulang pesan yang sama; relay ini *at-least-once*, bukan exactly-once. Untuk dataset resmi diperlukan deduplikasi berbasis `device_id` + `seq`/timestamp asli serta manajemen sumber data.

## Keamanan dan batasan

- Password broker H200 disimpan **hanya di H200**, dibaca remote sink dari `backend/.env`. Password lokal beda, disimpan hashed oleh Mosquitto dan diinput interaktif ke relay.
- Traffic ESP32 -> laptop tidak menggunakan TLS, hanya untuk **hotspot privat** yang kamu kontrol; jangan pakai Wi-Fi publik.
- Backend H200 tetap menggunakan nama topic lama, sehingga data dari rumah masuk ke DB development yang sama. Catat sumber dan waktu pengujian. Jangan memasukkannya dalam dataset GD525 resmi.
- SSH menggunakan verifikasi host key bawaan; jangan menambah `StrictHostKeyChecking=no`.
- Antrean SQLite lokal persisten dan dapat mengandung data sensor development. Folder data antrean diabaikan Git.
- Relay **satu arah**, dari sensor ke server. Rekomendasi balik untuk LED belum diteruskan ke ESP32 saat mode dev; perlu perluasan dua arah saat pengujian LED nanti.
- H200 dan laptop harus menyala, terhubung internet/Tailscale; tidak bisa disebut deployment 24/7 tanpa uji reliabilitas.
