# Dokumentasi CO₂ Classroom IoT

**Konteks:** tugas akhir prediksi CO₂ t+15 menit dengan GRU dan rekomendasi ventilasi untuk ruang GD525. **Status per 4 November 2026:** development; pengumpulan resmi GD525 belum dimulai.

## Indeks dokumen

| Dokumen | Isi |
|---|---|
| [architecture.md](architecture.md) | Arsitektur aktif vs target, wiring, alur data, fallback dan batasan |
| [data-contract.md](data-contract.md) | Topic MQTT, JSON ESP32 aktif, respons backend/API, schema, kontrak rancangan lama |
| [deployment-h200.md](deployment-h200.md) | Setup H200, .env, systemd, backup dan troubleshooting |
| [data-collection.md](data-collection.md) | Protokol pengambilan, audit, preprocessing 1 menit, event log, etika dan ML |
| [development-roadmap.md](development-roadmap.md) | Milestone, bukti pengujian dan pekerjaan berikutnya |
| [decisions-and-risks.md](decisions-and-risks.md) | Keputusan sudah diambil, hal yang masih terbuka, risiko dan mitigasi |

## Prinsip penggunaan

- Bedakan **sudah diuji**, **sudah ada di kode tetapi belum diuji end-to-end**, serta **rencana**. Jangan mengklaim GRU sudah dievaluasi pada data GD525.
- Jadikan perilaku firmware/backend dan hasil uji nyata sebagai acuan saat menemukan perbedaan dokumentasi; lalu revisi kontrak dengan terukur.
- Data development dan data penelitian resmi harus mempunyai provenance jelas. Label ruang `gd525` dalam topik tidak membuktikan sensor sedang berada di ruangan GD525.
- Jangan commit `.env`, `secrets.h`, database nyata, backup DB, private key atau PAT GitHub.
- Penghapusan dokumen lama `01-` sampai `05-` dilakukan **setelah** pemeriksaan silang dan commit migrasi, bukan dengan menghapus data operasional pada H200.

## Rujukan kode

`firmware/`, `backend/backend/app/`, `backend/database/schema.sql`, `ml/preprocessing/`, `deployment/systemd/`, `backups/`.

[README proyek](../README.md)
