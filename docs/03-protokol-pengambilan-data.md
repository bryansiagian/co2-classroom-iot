# 03. Protokol Pengambilan Data

Tujuan: data yang masuk konsisten, bisa dipertanggungjawabkan di laporan, dan cukup bersih untuk melatih serta mengevaluasi model. Angka yang bertanda *usulan* belum punya dasar dari pengukuran dan boleh diubah setelah uji awal.

## 1. Pemasangan perangkat

| Perangkat | Penempatan | Alasan |
|---|---|---|
| MH-Z19C (CO₂) | Setinggi zona napas penghuni duduk (usulan sekitar 1 sampai 1,5 m), di bagian tengah atau samping ruang. Jauh dari jendela, pintu, dan hembusan napas langsung | Dekat jendela atau pintu membaca udara luar, bukan udara yang dihirup kelas |
| DHT22 dalam | Dekat sensor CO₂, jauh dari proyektor dan sinar matahari langsung | Panas perangkat dan matahari membuat suhu terbaca terlalu tinggi |
| DHT22 luar | Di luar jendela, terlindung dari hujan dan sinar matahari langsung | Pembacaan suhu luar yang akurat |
| PIR HC-SR501 | Menghadap area duduk, sudut pandang tidak terhalang | PIR hanya mendeteksi gerakan |
| ESP32 dan LED | Tempat yang terlihat oleh dosen dan mahasiswa, dekat catu daya | LED hanya berguna jika terlihat |

Catat posisi final (foto dan sketsa denah) di `docs/` setelah pemasangan. Posisi sensor tidak boleh berpindah selama pengambilan data. Jika terpaksa dipindah, catat tanggal dan alasannya.

## 2. Persiapan sebelum data dihitung

1. **Pemanasan sensor CO₂**: MH-Z19C membutuhkan waktu pemanasan setelah dinyalakan. Periksa lama pastinya di datasheet, lalu buang pembacaan pada periode itu (firmware boleh mengirim `faults: ["co2"]` selama pemanasan).
2. **Kalibrasi dan baseline**: sensor seperti MH-Z19 umumnya punya fitur kalibrasi baseline otomatis (ABC) yang mengasumsikan CO₂ mencapai level udara luar secara berkala. Periksa di datasheet dan putuskan apakah dipakai (lihat dokumen 04). Apa pun keputusannya, catat di laporan.
3. **Uji udara luar**: sebelum pengambilan data resmi, letakkan sensor di tempat terbuka beberapa saat dan pastikan nilainya berada di kisaran udara luar yang wajar. Simpan hasilnya sebagai bukti sanity check.
4. **Sinkronisasi waktu**: ESP32 memakai NTP. Pastikan zona waktu tidak membuat selisih jam. Simpan dan kirim waktu dalam UTC.

## 3. Pengambilan data

| Parameter | Nilai | Catatan |
|---|---|---|
| Interval pesan | 1 menit | Sesuai proposal |
| Pembacaan internal | Setiap 10 detik (usulan), lalu dirata-rata per menit | Mengurangi noise tanpa menambah beban jaringan |
| PIR per menit | 1 jika ada gerakan pada menit itu | |
| Durasi | Usulan minimal 3 sampai 4 minggu hari kuliah efektif, termasuk akhir pekan atau hari kelas kosong | Perlu beragam situasi: kelas penuh, kelas setengah, kosong, jendela terbuka dan tertutup, cuaca berbeda |
| Penyimpanan mentah | Semua pesan disimpan apa adanya, tidak ada yang dihapus atau diubah | Pembersihan dilakukan pada salinan terpisah |

## 4. Catatan manual (event log)

Sensor tidak mengukur status jendela atau pintu (di luar lingkup TA). Catatan manual ini **bukan fitur sistem**, hanya alat bantu analisis agar lonjakan atau penurunan CO₂ di data bisa dijelaskan, misalnya saat mengevaluasi apakah flush benar-benar menurunkan CO₂.

Simpan sebagai CSV, satu baris per kejadian (contoh di `docs/contoh/event_log.csv` setelah dibuat):

| Kolom | Isi |
|---|---|
| `waktu_wib` | Format `YYYY-MM-DD HH:MM` |
| `jenis` | `kelas_mulai`, `kelas_selesai`, `jendela_buka`, `jendela_tutup`, `pintu_buka`, `pintu_tutup`, `flush_dilakukan`, `lainnya` |
| `jumlah_orang_perkiraan` | Angka atau kosong |
| `catatan` | Bebas, singkat |
| `pencatat` | Inisial |

Pencatatan tidak perlu lengkap setiap menit. Cukup kejadian yang jelas (kelas mulai atau selesai, jendela dibuka, rekomendasi diikuti atau tidak). Tanda "lengkap" atau "tidak lengkap" per hari membantu menentukan hari mana yang aman dipakai untuk evaluasi flush.

## 5. Kualitas data

| Situasi | Perlakuan |
|---|---|
| Nilai di luar rentang valid (lihat dokumen 02) | Tetap disimpan, ditandai `suspect`, dikecualikan dari pelatihan |
| Celah data 1 sampai 3 menit | Boleh diisi interpolasi linear pada salinan bersih, ditandai `imputed` |
| Celah lebih dari 3 menit | Tidak diisi. Jendela sliding 15 menit yang menyentuh celah itu dibuang |
| Lompatan CO₂ tidak wajar antar menit | Tandai untuk diperiksa manual sebelum dipakai |
| Sensor restart atau pemanasan ulang | Buang menit-menit pemanasan |
| Waktu `ts` tidak sinkron | Gunakan waktu terima dan tandai `ts_corrected` |

Ringkasan kualitas (persentase data hilang, jumlah `suspect`, jumlah celah) dihitung per hari dan dilampirkan di laporan.

## 6. Cadangan dan ekspor

- Ekspor harian dari database ke CSV (`sensor_reading`) dan simpan di luar perangkat server (drive tim atau repositori terpisah). Jangan commit data mentah besar ke Git.
- Folder data lokal (`data/`) masuk `.gitignore`. Contoh kecil yang aman boleh dikomit sebagai contoh format.
- Catat versi firmware dan versi kontrak data pada setiap periode pengambilan data.

## 7. Catatan untuk `ml/`

- Pembagian data train, validation, dan test dilakukan **berdasarkan urutan waktu**, bukan acak, supaya tidak bocor ke masa depan. Pembagian usulan awal: 70, 15, 15 persen. Sesuaikan jika ada hari yang tidak biasa.
- Jangan menormalisasi memakai statistik dari seluruh data. Hitung hanya dari bagian train.
- Pembanding minimal: persistence (nilai terakhir), lalu LSTM, lalu GRU, sesuai skenario E0 sampai E4 di proposal.
- Data sintetis hanya untuk menguji kode dan harus diberi label jelas. Hasilnya tidak dilaporkan sebagai hasil TA.

## 8. Privasi

Sistem tidak memakai kamera, mikrofon, atau data pribadi. PIR hanya menghasilkan nilai 0 atau 1 tanpa identitas. Catatan manual tidak memuat nama mahasiswa.
