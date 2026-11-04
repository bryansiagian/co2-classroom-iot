# Roadmap Pengembangan dan Status Tugas Akhir

**Diperbarui:** 4 November 2026. Status berdasarkan pengujian yang dilaporkan pada sesi pengembangan; belum merupakan hasil evaluasi ilmiah final.

## Tujuan akhir

Menghasilkan sistem berbasis IoT yang membaca kondisi ruang GD525, memprediksi CO₂ pada horizon 15 menit menggunakan GRU, serta menyampaikan rekomendasi ventilasi proaktif melalui dashboard dan indikator perangkat. Pengumpulan data nyata ditargetkan minimal 4 minggu, dengan dataset analisis interval 1 menit.

## Tahap dan status

| Tahap | Status | Bukti/keterangan |
|---|---|---|
| 1. Integrasi ESP32 + sensor | **Diuji** | MH-Z19C, DHT22, PIR; firmware V4.1 menerbitkan payload |
| 2. MQTT TLS | **Diuji** | ESP32 → Mosquitto H200 port 8883; `mosquitto_sub` menerima data |
| 3. Backend FastAPI dan ingest | **Diuji** | Backend H200 subscribe, memvalidasi dan menyimpan data |
| 4. Baseline prediksi & rekomendasi | **Diuji pada pipeline** | Persistence menghasilkan 15 horizon dan rekomendasi per sampel |
| 5. systemd backend | **Diuji** | Service `co2class-backend` enabled/active |
| 6. Backup SQLite | **Diuji di host yang sama** | Manual backup berhasil; timer harian dijadwalkan |
| 7. Audit kualitas data | **Audit awal lulus sementara** | 359 baris: 0 null/duplikat; 379 baris periode stabil: 8–12 detik seluruhnya |
| 8. Pengumpulan nyata ≥4 minggu | **Belum divalidasi/dinyatakan dimulai resmi** | Perlu kesiapan perangkat, jam, kestabilan dan backup |
| 9. Dataset 1 menit | **Script dan test diuji (development)** | 456 baris → 78 menit, 73 usable, 2 unit test OK; belum dataset resmi |
| 10. GRU vs baseline | **Belum selesai** | Training, tuning, validasi dan test kronologis |
| 11. Dashboard Next.js | **Integrasi akhir belum diverifikasi** | API, tren, prediksi, rekomendasi |
| 12. LED proaktif di ESP32 | **Belum diverifikasi end-to-end** | Subscription rekomendasi, status LED dan pengujian |
| 13. Evaluasi & laporan TA | **Berjalan/direncanakan** | MAE, RMSE, R² dan evaluasi rekomendasi |

## Milestone A — Stabilkan pengumpulan data

**Output:** sumber data nyata dengan timestamp andal dan prosedur pemantauan.

- [x] ESP32 kirim data sensor ke broker MQTT TLS.
- [x] Backend H200 dapat menerima data dan terus berjalan via systemd.
- [x] Backup terjadwal di host sama.
- [ ] Selesaikan clock ESP32; firmware V4.1 menggunakan fallback waktu kompilasi jika NTP gagal.
- [ ] Audit kestabilan 24–72 jam dan pengujian setelah restart.
- [ ] Siapkan backup off-server, retensi, dan restore test.
- [ ] Catat provenance, metadata kelas, posisi alat, dan jadwal.
- [ ] Tentukan titik awal pengambilan data resmi 4 minggu.

## Milestone B — Dataset dan baseline

**Output:** data mentah terarsip dan dataset 1 menit tervalidasi.

- [x] Jalankan audit awal data development; otomasi audit harian belum ada.
- [x] Pemeriksaan awal interval, duplikasi, missing dan rentang telah dijalankan; audit berkelanjutan belum ada.
- [x] Implementasikan dan uji `ml/preprocessing/resample_sensor_data.py` untuk development.
- [ ] Pisahkan train/validation/test secara kronologis.
- [ ] Hitung baseline persistence pada test set terpisah.

## Milestone C — GRU dan rekomendasi

**Output:** model terlatih dan hasil perbandingan yang dapat direproduksi.

- [ ] Tetapkan panjang lookback dan fitur input.
- [ ] Pelatihan/tuning GRU hanya memakai rentang train/validation.
- [ ] Evaluasi MAE, RMSE, R² dan hasil prediksi t+15.
- [ ] Bandingkan terhadap persistence dan, jika relevan, LSTM.
- [ ] Evaluasi crossing threshold, precision/recall/F1 dan lead time.
- [ ] Pertimbangkan hysteresis dan risiko false alarm.
- [ ] Catat versi model, data split, seed dan konfigurasi eksperimen.

## Milestone D — Integrasi aplikasi

**Output:** rekomendasi dapat dilihat dan diuji ujung ke ujung.

- [ ] API menyajikan status data terbaru, histori, prediksi, rekomendasi dan indikator stale.
- [ ] Dashboard Next.js memvisualisasikan hasil dengan benar.
- [ ] ESP32 menerima pesan rekomendasi dan mengendalikan LED sesuai keputusan.
- [ ] Uji kondisi MQTT terputus, restart, sensor error, dan data stale.
- [ ] Uji kelayakan sistem dalam skenario kelas tanpa kendali ventilasi otomatis.

## Milestone E — Dokumentasi dan serah-terima

- [x] Konfigurasi systemd dan script backup dicatat dalam repository.
- [ ] Panduan instalasi, troubleshooting dan restore diuji oleh anggota tim lain.
- [ ] Dokumentasikan diagram, pemetaan pin dan aturan keputusan.
- [ ] Siapkan tabel/plot hasil eksperimen dan pembahasan batasan penelitian.
- [ ] Audit keamanan repository (secret, token, kunci, file database).

## Prioritas pekerjaan berikutnya

1. **Pertahankan audit berkelanjutan** database H200; audit awal development sudah berhasil.
2. **Perbaiki ketahanan deployment**: clock ESP32, monitoring kehilangan data dan backup off-server.
3. **Tetapkan awal periode resmi** pengumpulan data, sekaligus metadata lapangan.
4. **Bangun sliding window kontinu dan baseline**, melanjutkan script agregasi 1 menit yang sudah diuji.
5. **Integrasikan model, dashboard dan LED**, lalu evaluasi end-to-end.

## Bukti teknis pengujian singkat

- Backend di laptop pernah menghasilkan **87 sensor, 1.305 prediksi, 87 rekomendasi**.
- Backend H200 menghasilkan **4 sensor, 60 prediksi, 4 rekomendasi** saat uji awal.
- Setelah aktif melalui systemd, uji 30 detik menunjukkan kenaikan **+3 sensor, +45 prediksi, +3 rekomendasi**.
- Backup SQLite H200 diuji secara manual dan sebagai service one-shot dengan `status=0/SUCCESS`.

Angka di atas hanya bukti fungsi pipeline pada tahap pengembangan, **bukan** ukuran akurasi model atau hasil data 4 minggu.

## Dokumen terkait

[README](../README.md) · [Arsitektur](architecture.md) · [Deployment](deployment-h200.md) · [Data collection](data-collection.md)

[Kontrak data](data-contract.md) · [Keputusan dan risiko](decisions-and-risks.md)
