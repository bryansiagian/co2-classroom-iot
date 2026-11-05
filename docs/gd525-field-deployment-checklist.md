# Checklist pra-pemasangan sensor di GD525

Status: **rencana, belum terlaksana**. Dataset development dari luar GD525 **tidak** boleh dicampur dengan dataset penelitian resmi.

## Sebelum pemasangan

- [ ] Dapatkan izin penggunaan ruang serta pemasangan alat dan akses listrik/jaringan.
- [ ] Tetapkan titik pemasangan dan dokumentasikan posisi/ketinggian sensor; hindari hembusan AC langsung, ventilasi, dan panas laptop.
- [ ] Pastikan adaptor 5 V 2 A stabil, kabel terlindungi, tidak mengganggu aktivitas kelas, dan perangkat tidak mudah terlepas.
- [ ] Periksa kalibrasi/penyetelan MH-Z19C (termasuk kebijakan ABC sesuai datasheet dan kondisi penempatan); catat tanggal dan prosedur.
- [ ] Pastikan DHT22, MH-Z19C, PIR berfungsi dan respons sensor masuk akal.
- [ ] Pastikan `HW-Mahasiswa`, MQTT TLS 8883, dan sertifikat broker bisa dipakai di GD525.
- [ ] **Selesaikan masalah waktu ESP32 setelah power-cycle:** NTP gagal dan fallback build-time belum cukup untuk pengoperasian unattended 4 minggu.
- [ ] Pastikan H200: `systemctl is-active mosquitto` dan `systemctl is-active co2class-backend` menunjukkan `active`.
- [ ] Lakukan pengujian putus-sambung listrik/Wi-Fi, periksa reconnect tanpa campur data antarsesi.
- [ ] Siapkan backup database di lokasi kedua (di luar H200), bukan hanya file cadangan dalam server yang sama.

## Awal sesi resmi

- [ ] Tetapkan `collection_session_id` / penanda dataset **resmi**, waktu mulai UTC/WIB, ruangan, dan operator.
- [ ] Pisahkan penyimpanan atau metadata data development dan data resmi; jangan hapus arsip development.
- [ ] Catat jadwal perkuliahan, perkiraan jumlah hadir, kondisi pintu/jendela, penggunaan AC/kipas, dan aktivitas ventilasi manual.
- [ ] Verifikasi 30–60 menit pertama: interval teramati ~10 detik, tidak ada duplikasi, missing values, atau koneksi berulang.
- [ ] Pertahankan raw data; agregasi 1 menit dilakukan di pipeline terpisah dengan penanda kelengkapan.
- [ ] Pantau ketersediaan data dan status systemd setiap hari; dokumentasikan listrik padam, jaringan putus, perpindahan posisi alat.

## Setelah data terkumpul

- [ ] Simpan salinan mentah dan audit resmi, jaga tanggal sesi.
- [ ] Split kronologis dan fitting scaler pada train saja; hindari overlap input/target antar-split.
- [ ] Jangan menyimpulkan performa GRU dari pengujian data sintetis ataupun development.
