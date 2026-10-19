# 04. Keputusan Terbuka dan Risiko

Daftar ini untuk dibahas bertiga dan dicentang setelah ada keputusan. Tulis hasilnya di kolom "Keputusan" lalu perbarui dokumen terkait.

## A. Keputusan yang perlu disepakati

| # | Pertanyaan | Pilihan atau pertimbangan | Keputusan |
|---|---|---|---|
| 1 | Di mana broker MQTT dan backend berjalan? | Laptop di ruang kelas, Raspberry Pi, atau server (misalnya VPS atau EC2). Pilihan menentukan apakah data tetap masuk saat laptop mati | |
| 2 | Database apa? | SQLite (paling sederhana), PostgreSQL (lebih rapi untuk deret waktu dan beberapa pengguna) | |
| 3 | Bagaimana ESP32 tersambung ke jaringan? | Wi-Fi kampus (bisa memakai captive portal atau WPA2-Enterprise yang sulit untuk ESP32), atau hotspot khusus. Perlu diuji lebih awal | |
| 4 | Apakah fitur kalibrasi otomatis (ABC) MH-Z19C dipakai? | Aktif: sensor mengoreksi sendiri, tetapi bisa bergeser jika ruang jarang mencapai udara segar. Nonaktif: perlu kalibrasi manual berkala. Periksa datasheet | |
| 5 | Bagaimana DHT22 luar tersambung ke ESP32? | Dikabel keluar jendela dari ESP32 yang sama (asumsi dokumen ini), atau ESP32 kedua. Kabel panjang bisa mengganggu pembacaan | |
| 6 | Aturan lama flush (3, 4, 5 menit) | Draf di dokumen 02 berdasar tingkat puncak prediksi. Perlu dasar atau diganti nilai tetap | |
| 7 | Siapa pemilik tiap folder? | Contoh: firmware, backend dan database, ML. Frontend dan integrasi ke pemilik repo | |
| 8 | Strategi cabang Git | Contoh: `main` stabil, cabang `feat/...` per fitur, merge lewat Pull Request | |
| 9 | Siapa yang mengisi catatan manual dan kapan? | Perlu jadwal sederhana agar tidak bergantung pada satu orang | |
| 10 | Bagaimana cara menjalankan saat demo? | Data langsung, atau rekaman data (replay) sebagai cadangan jika jaringan bermasalah | |

## B. Risiko yang diketahui

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Wi-Fi kampus menolak ESP32 | Data tidak masuk | Uji di GD 525 sebelum pemasangan resmi. Siapkan hotspot cadangan |
| ESP32 atau sensor mati berjam-jam | Celah data, jendela pelatihan terbuang | Last Will MQTT, status "Terputus" di dashboard, simpan buffer di ESP32, pengecekan harian |
| Pergeseran baseline sensor CO₂ | Prediksi dan ambang bergeser | Uji udara luar berkala, catat setiap kalibrasi |
| Data kurang beragam (cuaca, jumlah mahasiswa) | Model tidak generalisasi, evaluasi tidak meyakinkan | Perpanjang pengambilan data, catat kondisi, jujur soal batas klaim di laporan |
| PIR tidak mendeteksi orang yang diam | Okupansi terbaca rendah saat kelas penuh | Perlakukan PIR sebagai indikator, bukan jumlah orang. Jangan jadikan fitur utama tanpa diuji |
| Prediksi baik tetapi rekomendasi tidak diikuti | Nilai guna sulit dibuktikan | Rancang evaluasi proaktif vs reaktif (lead time, alarm palsu) dan catat apakah rekomendasi diikuti |
| Tenggat dan pembagian kerja tidak seimbang | Salah satu bagian terlambat | Kontrak data dikunci lebih dulu agar semua bagian bisa jalan paralel |

## C. Pekerjaan lanjutan untuk `docs/`

- [ ] Diagram blok perangkat keras (pin ESP32 ke setiap sensor dan LED)
- [ ] Foto dan denah pemasangan di GD 525
- [ ] Contoh `event_log.csv`
- [ ] Gambaran umum sistem untuk lampiran proposal (diturunkan dari dokumen 01)
