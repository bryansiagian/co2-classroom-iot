# Dokumentasi TA

Prediksi Konsentrasi CO₂ Jangka Pendek dan Rekomendasi Ventilasi Proaktif Ruang Kelas Berbasis IoT Menggunakan GRU.

| Dokumen | Isi |
|---|---|
| [01-arsitektur.md](01-arsitektur.md) | Gambaran umum sistem, komponen, alur data, dan pembagian tanggung jawab antar folder |
| [02-kontrak-data.md](02-kontrak-data.md) | Topik MQTT, format pesan sensor, skema API ke dashboard, dan aturan rekomendasi |
| [03-protokol-pengambilan-data.md](03-protokol-pengambilan-data.md) | Cara memasang sensor, mengambil data, mencatat kejadian manual, dan menjaga kualitas data |
| [04-keputusan-terbuka.md](04-keputusan-terbuka.md) | Hal yang masih perlu disepakati tim, dan risiko yang diketahui |

Aturan penggunaan: kalau kontrak data di `02-kontrak-data.md` berubah, ubah dokumen ini lebih dulu, lalu sesuaikan `firmware/`, `backend/`, `database/`, `ml/`, dan `frontend/`.
