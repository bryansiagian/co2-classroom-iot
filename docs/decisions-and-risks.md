# Keputusan Desain, Isu Terbuka, dan Risiko

**Status:** 4 November 2026; development, belum dimulai pengumpulan resmi di GD525. Memigrasikan keputusan terbuka dari `04-keputusan-terbuka.md` tanpa menganggap semua rancangan sudah terealisasi.

## A. Keputusan yang sudah diambil/diuji

| Topik | Keputusan saat ini | Batasan |
|---|---|---|
| Broker | Mosquitto pada server H200, MQTT/TLS TCP 8883 | IP `172.22.44.29` spesifik jaringan kampus |
| Backend | FastAPI + Paho MQTT, dijalankan oleh `co2class-backend.service` | Backend API loopback `127.0.0.1:8000`; uji jangka panjang belum selesai |
| Penyimpanan | SQLite `backend/backend/data/co2class.db` di H200 | Perlu pemisahan sesi development/resmi dan strategi off-server |
| Cadangan | SQLite Backup API, timer harian 17:00 UTC/00:00 WIB | Belum ada retensi, restore test dan off-server backup |
| Jaringan ESP32 | SSID kampus `HW-Mahasiswa`, TLS ke H200 | Uji khusus di GD525 belum terdokumentasi |
| Sensor | MH-Z19C, DHT22 dalam, HC-SR501/PIR | PIR tidak menghitung penghuni; DHT22 luar belum diterapkan |
| Interval | ESP32 V4.1 publish ~10 detik; dataset ML diagregasi 1 menit | Tidak sama dengan rancangan awal publish 1 menit |
| Model online | Persistence untuk sementara | GRU belum dilatih/dievaluasi pada dataset penelitian resmi |
| Rekomendasi | `none/watch/flush` berdasarkan ambang prediksi | LED proaktif belum diuji end-to-end |

## B. Keputusan yang belum final

| Prioritas | Pertanyaan | Tindakan / bukti yang dibutuhkan |
|---|---|---|
| Tinggi | Kapan tepatnya sesi penelitian resmi GD525 dimulai? | Tetapkan tanggal UTC/WIB, posisi alat, kode commit dan catatan sesi; jangan campur data development |
| Tinggi | Bagaimana sinkronisasi waktu ESP32 jika NTP publik terhalang? | Cari sumber waktu tepercaya yang bisa diakses pada Wi-Fi kampus; fallback waktu kompilasi hanya workaround |
| Tinggi | Apa kebijakan kalibrasi dan ABC MH-Z19C? | Baca datasheet sensor aktual, validasi udara luar/referensi, catat pengaturan dan kejadian kalibrasi |
| Tinggi | Bagaimana menangani pesan hilang, downtime dan pengulangan? | Putuskan QoS, `seq`, retry buffer, ID perangkat dan deteksi duplikat sebelum empat minggu |
| Tinggi | Bagaimana menjaga backup saat H200 gagal? | Backup terpisah dari server, retensi, verifikasi integritas dan uji restore |
| Sedang | Apakah perlu sensor DHT22 luar? | Satu DHT22 dalam adalah implementasi aktif; nilai luar di schema tetap opsional |
| Sedang | Apakah aturan lama flush 3/4/5 menit valid? | Uji hasil nyata, dasar pustaka/eksperimen, precision/recall/F1 dan lead time |
| Sedang | Siapa mengisi event log dan foto posisi sensor? | Tetapkan pembagian tugas tim dan jadwal pencatatan |
| Sedang | Strategi kontribusi Git dan kepemilikan modul? | Dokumentasikan alur branch/PR, review, pengujian, dan deploy |
| Sedang | Rencana demo jika internet/jaringan terputus? | Uji replay yang ditandai sebagai simulasi; jangan dianggap data nyata |

## C. Risiko dan mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Wi-Fi atau broker terputus | Gap data dan kehilangan pembacaan | Pantau interval, reconnect, evaluasi QoS/buffer/sequence dan alarm stale |
| ESP32 kehilangan daya atau restart | Gap, jam salah, sensor warm-up | Adaptor stabil, restart test, prosedur warm-up, sumber waktu andal |
| Sensor drift/ABC salah | Baseline CO₂ tidak representatif | Catat kalibrasi, uji udara luar, periksa datasheet MH-Z19C |
| DHT22 terpapar panas perangkat/sinar matahari | Suhu bias | Jauhkan dari sumber panas, dokumentasikan posisi |
| PIR tidak mendeteksi orang diam | Salah tafsir okupansi | Perlakukan sebagai aktivitas biner, bukan hitungan kehadiran |
| Dataset kurang beragam | GRU tidak generalisasi | Kumpulkan hari/jadwal kelas bervariasi, catat peristiwa dan keterbatasan |
| Kebocoran masa depan dalam ML | Metrik terlalu optimistis | Split kronologis, scaler hanya fit train, window tidak melewati gap |
| Backup hanya satu host | Dataset hilang jika host rusak | Jadwalkan off-server backup, retensi dan restore test |
| Rekomendasi tidak dipatuhi | Nilai guna tidak dapat diklaim | Catat penggunaan ventilasi manual, bandingkan proaktif vs reaktif |
| Kebocoran secret Git | Akun MQTT/server disalahgunakan | `.gitignore`, permission file, review staged diff, rotasi token bila bocor |

## D. Pekerjaan dokumentasi lapangan

- [ ] Diagram pin final, foto dan denah posisi sensor GD525.
- [ ] Contoh event log dan petugas pencatat.
- [ ] Berita acara pemasangan/kalibrasi; catatan restart/perubahan firmware.
- [ ] Registrasi sesi pengambilan data resmi dan periode penelitian.
- [ ] Bukti backup restore dan laporan audit harian/mingguan.

Lihat [kontrak data](data-contract.md), [protokol](data-collection.md), [roadmap](development-roadmap.md).
