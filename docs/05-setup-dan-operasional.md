# Setup & Panduan Operasional — CO₂ Classroom IoT

> **Status: prototipe / pengujian integrasi (3 November 2026).** Dokumen ini mencatat **sistem yang sudah diuji**, cara menjalankannya, dan arah integrasi selanjutnya. Ini **bukan** klaim bahwa seluruh aplikasi di repository sudah siap produksi. Jika dokumen lain berbeda, jangan otomatis mengubah server yang sudah berjalan; lakukan peninjauan dan keputusan perubahan terlebih dahulu.

## 1. Tujuan proyek

Proyek ini bertujuan mengukur kondisi ruang kelas melalui IoT, mengumpulkan data deret waktu, memprediksi konsentrasi CO₂ **15 menit ke depan** dengan GRU, dan memberi **rekomendasi ventilasi proaktif** melalui dashboard/indikator. Tidak ada kontrol ventilasi otomatis.

Rencana pengambilan data penelitian: **satu ruang kelas (GD525)**, interval dataset utama **1 menit**, target durasi **minimal 4 minggu**. Fitur yang direncanakan: CO₂ (ppm), suhu (°C), kelembapan relatif (%RH), dan indikator aktivitas PIR (0/1). PIR **tidak** menghitung jumlah orang dan `0` **tidak membuktikan ruangan kosong**.

## 2. Prinsip pengembangan

1. **H200 dan pengujian fisik yang berhasil menjadi baseline implementasi sementara.** Repository harus diselaraskan dengan hasil nyata; jangan mengubah broker, ACL, topik, atau skema data yang bekerja hanya untuk mengikuti rancangan lama.
2. Semua perubahan harus **diuji bertahap**: sensor → MQTT → penyimpanan → pemrosesan data → model → dashboard.
3. Pisahkan tegas **data demo/sintetis** dari **data sensor nyata**. Metrik model dari demo tidak boleh diklaim sebagai hasil penelitian.
4. **Jangan commit** password, private key, dataset penelitian mentah, file database berisi data nyata, atau rahasia jaringan ke GitHub.
5. Dokumentasikan keputusan perubahan kontrak data dan kompatibilitas sebelum migrasi.

## 3. Arsitektur yang sudah diuji

```text
[MH-Z19C] [DHT22] [PIR HC-SR501]
         \    |    /
         [ESP32 DevKit V1]
                 |
          Wi-Fi HW-Mahasiswa
                 |
        MQTT over TLS :8883
                 |
        [Mosquitto pada H200]
                 |
       topic classroom/gd525/sensors
                 |
       [Python collector.py]
                 |
         [SQLite gd525_test.db]
```

**Terbukti berjalan:** ESP32 membaca sensor nyata, terhubung ke Wi-Fi, melakukan publish MQTT TLS, dan H200 menerima pesan melalui subscriber Python. ESP32 juga telah diuji beroperasi dengan adaptor 5V tanpa USB laptop. **Belum terbukti terintegrasi end-to-end:** collector permanen dalam backend repository, inferensi GRU real-time, dashboard, LED rekomendasi, dan pengumpulan dataset penelitian 4 minggu.

### Lingkungan dan komponen

| Bagian | Konfigurasi pengujian |
|---|---|
| ESP32 | ESP32 DevKit V1, firmware Arduino IDE |
| CO₂ | MH-Z19C, UART 9600 bps |
| Suhu & RH | DHT22 |
| Aktivitas | PIR HC-SR501 |
| Server | Ubuntu H200, hostname `TATI-BRYAN` |
| IP broker pada jaringan pengujian | `172.22.44.29` (IP privat; cek ulang jika berubah) |
| Broker | Mosquitto, TLS TCP `8883` |
| Topic sensor **aktif** | `classroom/gd525/sensors` |
| Akun publish ESP32 | `esp32_gd525` |
| Akun subscribe collector | `backend_gd525` |
| Python collector uji | `~/gd525-iot-test/collector.py` |
| Database uji | `~/gd525-iot-test/gd525_test.db` (SQLite) |
| Firmware uji terbaru | V3, motion latch PIR, publish setiap 10 detik, berhenti setelah 15 menit |

> **Perhatian:** Beberapa rancangan awal repository mungkin menggunakan nama topic/field berbeda. Tabel di atas adalah **konfigurasi pengujian yang benar-benar digunakan**, bukan kontrak final seluruh aplikasi.

## 4. Wiring ESP32

| Komponen | Pin komponen | ESP32 |
|---|---|---|
| MH-Z19C | VCC | VIN / 5V |
| MH-Z19C | GND | GND |
| MH-Z19C | TX | GPIO26 (RX2) |
| MH-Z19C | RX | GPIO25 (TX2) |
| DHT22 | VCC | 3V3 |
| DHT22 | GND | GND |
| DHT22 | DATA | GPIO4 |
| PIR HC-SR501 | VCC | VIN / 5V |
| PIR HC-SR501 | GND | GND |
| PIR HC-SR501 | OUT | GPIO27 |

Gunakan **common ground**. DHT22 tipe sensor tanpa modul biasanya membutuhkan resistor pull-up DATA ke 3V3; periksa modul yang digunakan. Pastikan sinyal yang masuk GPIO ESP32 tidak melebihi batas 3,3V. Gunakan adaptor **5V 2A** yang sesuai untuk pengoperasian mandiri; jangan menghubungkan dua sumber daya USB/adaptor sembarangan.

## 5. Persiapan firmware

**Prasyarat:** Arduino IDE, board ESP32 terpasang, library `PubSubClient` dan `DHT sensor library` beserta dependensinya, kabel USB data, akses jaringan broker.

1. Buka sketch firmware pengujian yang sudah berhasil (simpan versi sebelumnya sebelum mengganti).
2. Periksa SSID, IP server, port, topic, pin, serta kredensial MQTT. **Jangan kirim password ke chat atau commit ke Git.**
3. Untuk TLS gunakan **sertifikat publik** `/etc/mosquitto/certs/server.crt` sebagai `SERVER_CERT`, dengan format PEM lengkap dari `-----BEGIN CERTIFICATE-----` sampai `-----END CERTIFICATE-----`. **Jangan gunakan** `server.key` dan jangan memakai `setInsecure()` sebagai solusi permanen.
4. Arduino IDE: pilih board dan port yang benar → **Verify** (kompilasi) → **Upload** (flash). Verify saja **tidak** mengganti firmware.
5. Buka Serial Monitor `115200` baud. Pastikan muncul koneksi Wi-Fi, `MQTT TERHUBUNG!`, pembacaan sensor, dan `Publish berhasil!`.
6. Setelah berhasil, ESP32 dapat dipindah dari USB laptop ke adaptor 5V. Pemindahan daya akan me-restart ESP32.

### Interval dan PIR

Firmware **V3 pengujian** memantau PIR sekitar setiap **50 ms** menggunakan *motion latch*, lalu membaca CO₂/DHT22 dan publish setiap **10 detik**. `pir:1` berarti setidaknya ada satu HIGH yang tertangkap dalam periode pengamatan, **bukan** jumlah orang atau bukti keberadaan terus-menerus.

Hasil uji PIR terpisah menunjukkan HIGH sekitar **0,88–0,90 detik** dan LOW sekitar **2,06–2,40 detik** saat banyak aktivitas di meja. Itulah alasan sampling sesaat setiap 10/60 detik bisa melewatkan gerakan.

**Keterbatasan V3 yang perlu diperbaiki sebelum pengambilan data final:** sampling 50 ms tidak dijamin ketika operasi jaringan/UART memblokir; pengelolaan reset latch saat publish perlu ditinjau agar interval tidak tercampur. Uji juga perilaku PIR tanpa gerakan. Dataset final direncanakan **1 menit**, dengan agregasi aktivitas PIR per menit yang didefinisikan secara eksplisit.

### Waktu/TLS

Firmware pengujian sementara mengatur waktu ESP32 berdasarkan **waktu kompilasi Arduino IDE dengan asumsi WIB (UTC+7)** karena NTP sebelumnya belum berfungsi. Ini hanya workaround agar pemeriksaan masa berlaku sertifikat TLS bisa berjalan; **bukan sumber timestamp penelitian yang andal**. Waktu yang meleset dapat menyebabkan kegagalan TLS. Untuk data final, siapkan sinkronisasi waktu yang andal, dan gunakan timestamp penerimaan server yang tervalidasi serta dokumentasikan latensi.

## 6. Menjalankan collector di H200

Masuk SSH ke server menggunakan akses yang telah diberikan administrator. Jalankan:

```bash
cd ~/gd525-iot-test
source .venv/bin/activate
```

Jika virtual environment atau dependensi belum ada pada instalasi baru (jangan menimpa instalasi yang sudah bekerja):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "paho-mqtt==2.1.0"
```

Siapkan password **akun backend**, bukan password akun ESP32, secara interaktif agar tidak masuk ke riwayat shell:

```bash
read -rsp "Password MQTT backend: " MQTT_PASSWORD
echo
export MQTT_PASSWORD
python collector.py
```

Output sukses umumnya:

```text
=== GD525 COLLECTOR ===
Durasi penyimpanan: 15 menit
MQTT TERHUBUNG!
Subscribe: classroom/gd525/sensors
[...+00:00] CO2=... ppm | T=... C | RH=...% | PIR=...
```

**Penting:** `MQTT TERHUBUNG!` pada collector hanya membuktikan subscriber terhubung; pastikan ada baris data masuk untuk membuktikan publish ESP32 diterima. Collector uji menyimpan data ke SQLite **hanya ketika prosesnya berjalan**; broker MQTT sendiri tidak otomatis menulis ke database. Hentikan dengan `Ctrl+C` bila perlu.

### Periksa data SQLite

Jika CLI `sqlite3` tersedia:

```bash
cd ~/gd525-iot-test
sqlite3 gd525_test.db
```

Di prompt SQLite:

```sql
.headers on
.mode column
SELECT COUNT(*) AS total FROM sensor_readings;
SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 10;
.quit
```

Skema pengujian:

| Kolom | Tipe |
|---|---|
| `id` | INTEGER, primary key |
| `received_at_utc` | TEXT, timestamp penerimaan UTC |
| `co2` | INTEGER |
| `temperature` | REAL |
| `humidity` | REAL |
| `pir` | INTEGER (0/1) |

UTC berbeda **+7 jam dari WIB**. Jangan mengubah timestamp UTC dengan menambah 7 jam dalam penyimpanan; konversi hanya untuk tampilan.

### Jangan campur sesi uji

Firmware pernah menggunakan payload simulasi/hard-coded. Pastikan data simulasi tidak bercampur dengan data sensor asli. **Setelah collector berhenti**, cadangkan/rename database pengujian lama sebelum membuat sesi baru, misalnya:

```bash
cd ~/gd525-iot-test
mv gd525_test.db gd525_test_sebelumnya.db
```

Lakukan hanya jika file lama memang ada dan tidak sedang digunakan. Jangan menimpa backup. Untuk penelitian final gunakan pemisahan `demo` dan `real` yang eksplisit, plus metadata sesi dan versi firmware.

## 7. Format payload MQTT yang aktif

Topic: `classroom/gd525/sensors`

```json
{
  "co2": 855,
  "temperature": 25.70,
  "humidity": 76.40,
  "pir": 1
}
```

| Field | Arti |
|---|---|
| `co2` | CO₂ dalam ppm |
| `temperature` | Suhu dalam °C |
| `humidity` | Kelembapan relatif dalam %RH |
| `pir` | Indikator aktivitas yang terdeteksi (0/1) |

Format ini adalah **format uji aktif**, bukan kontrak data final. Timestamp saat ini diberikan collector (`received_at_utc`), bukan payload ESP32. QoS publish firmware pengujian `PubSubClient.publish()` adalah **QoS 0**; untuk kebutuhan reliabilitas penelitian perlu keputusan terpisah tentang QoS, buffer offline, deduplikasi, dan kehilangan data.

## 8. Pemeriksaan dan troubleshooting

| Gejala | Pemeriksaan awal |
|---|---|
| `MQTT TERHUBUNG!` tetapi tidak ada baris collector | Pastikan ESP32 masih dalam masa uji 15 menit, topic sama, firmware benar-benar di-upload, dan ada `Publish berhasil!` |
| `TLS error: -8576` / format X.509 invalid | Sertifikat `SERVER_CERT` tidak lengkap, placeholder belum diganti, atau PEM berubah; gunakan `server.crt` publik yang benar |
| TLS gagal karena waktu | Periksa waktu ESP32 dan masa berlaku sertifikat; perbaiki sinkronisasi waktu, jangan menonaktifkan validasi TLS |
| MQTT `Not authorized` | Periksa kredensial akun yang benar dan ACL/topic; jangan mencetak password |
| PIR selalu `0` pada sampling sesaat | Uji GPIO27 terpisah; HIGH bisa berlangsung kurang dari interval sampling; gunakan motion latch |
| PIR selalu `1` | Uji saat tidak ada aktivitas, hold time/mode trigger, dan logika reset latch |
| RH mendekati 100% | Verifikasi kondisi ruangan, lokasi sensor, potensi kondensasi, dan bandingkan dengan alat referensi |
| CO₂ melonjak cepat | Cek warm-up, catu daya, ventilasi, kalibrasi, lokasi sensor, dan log kualitas data; jangan langsung anggap semua nilai valid |

Untuk membaca sertifikat publik di H200:

```bash
sudo cat /etc/mosquitto/certs/server.crt
openssl x509 -in /etc/mosquitto/certs/server.crt -noout -subject -issuer -dates
```

**Jangan membaca/membagikan private key** `/etc/mosquitto/certs/server.key`. Bila password pernah terungkap, rotasi melalui administrator/server dan update perangkat.

## 9. Roadmap implementasi (belum semuanya selesai)

- [x] Uji masing-masing sensor dan wiring dasar.
- [x] Uji publish ESP32 → Mosquitto TLS H200.
- [x] Uji ESP32 mandiri memakai adaptor 5V.
- [x] Uji Python collector → SQLite.
- [x] Uji PIR terpisah dan motion latch V3.
- [ ] Verifikasi PIR pada kondisi tanpa aktivitas; perbaiki reset latch dan blocking sampling.
- [ ] Validasi CO₂ dan RH, warm-up, penempatan sensor, dan prosedur kalibrasi.
- [ ] Tetapkan waktu/timestamp tepercaya dan pencatatan kualitas data.
- [ ] Tetapkan firmware final **interval 1 menit**, pengukuran/agregasi per menit, dan kebijakan data hilang.
- [ ] Audit dan sesuaikan kontrak data di repository dengan implementasi nyata.
- [ ] Integrasikan collector permanen ke `backend/` tanpa mencampur `demo` dan `real`.
- [ ] Jalankan pengambilan data nyata minimal 4 minggu dengan log kondisi ruang.
- [ ] Audit, cleaning, split kronologis, dan pelatihan/evaluasi GRU vs LSTM vs persistence pada **data nyata**.
- [ ] Integrasikan inferensi GRU, rekomendasi ventilasi, dashboard, dan indikator LED.
- [ ] Uji sistem end-to-end, dokumentasikan metrik, kegagalan, dan hasil penelitian.

Ambang operasional **rencana penelitian**: `<800 ppm` aman, `800–999 ppm` waspada, `>=1000 ppm` rekomendasi buka ventilasi, `>=1500 ppm` kritis. Ambang ini merupakan **aturan keputusan proyek**, bukan pengganti standar regulasi atau bukti bahwa model sudah tervalidasi.

## 10. Panduan untuk developer / AI assistant berikutnya

Sebelum menyarankan perubahan, baca dokumen ini dan periksa kode yang benar-benar ada pada branch aktif. **Jangan mengasumsikan** seluruh rancangan awal di `docs/` telah diimplementasikan.

**Baseline operasional saat dokumen ini ditulis:**
- Server H200 sudah memiliki Mosquitto TLS, akun/ACL, dan collector pengujian yang bekerja.
- ESP32 V3 berhasil publish data sensor nyata; PIR motion latch menunjukkan `pir:1` saat ada aktivitas.
- Pengujian masih dibatasi 15 menit; interval 10 detik adalah **uji teknis**, bukan konfigurasi dataset penelitian final.
- Nama topic dan JSON yang aktif tercantum pada bagian 7.
- Kode `collector.py` pengujian berada **di server**, belum tentu identik dengan kode `backend/` GitHub.
- Pipeline ML di repository perlu diaudit terpisah; **hasil dataset sintetis tidak boleh diperlakukan sebagai hasil eksperimen nyata**.

**Sebelum memodifikasi:** tanyakan/cek tujuan perubahan, file aktual, output log, kompatibilitas topic dan ACL, konsekuensi untuk data lama, serta prosedur rollback. Lakukan perubahan kecil yang bisa diverifikasi. Jangan mengganti konfigurasi H200 yang sudah bekerja tanpa alasan dan persetujuan yang jelas.

## 11. Referensi dokumentasi internal

Dokumen lain yang tersedia/direncanakan pada repository:

- `docs/01-arsitektur.md`
- `docs/02-kontrak-data.md`
- `docs/03-protokol-pengambilan-data.md`
- `docs/04-keputusan-terbuka.md`

Dokumen ini **tidak mengaudit isi** keempat berkas tersebut. Perbedaan apa pun harus dicatat sebagai keputusan terbuka dan diselaraskan secara eksplisit.

---

**Usulan lokasi:** `docs/05-setup-dan-operasional.md`  
**Status dokumen:** living document; perbarui setiap kali konfigurasi yang telah diverifikasi berubah.
