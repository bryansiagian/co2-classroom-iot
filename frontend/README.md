# Frontend: Dashboard CO₂ Ruang Kelas

Dashboard Next.js untuk menampilkan CO₂ terukur, prediksi 15 menit (GRU), dan rekomendasi ventilasi.

## Menjalankan

```bash
npm install
cp .env.local.example .env.local   # kosongkan NEXT_PUBLIC_API_URL untuk data simulasi
npm run dev                        # http://localhost:3000
```

## Struktur

- `app/` halaman dan layout
- `components/` Gauge, RecommendationCard, StatTile, CO2Chart, EventList, Dashboard
- `lib/types.ts` kontrak data antara backend dan frontend
- `lib/api.ts` data simulasi atau `GET {NEXT_PUBLIC_API_URL}/api/dashboard`
- `lib/mock.ts` generator data simulasi (hapus setelah backend siap)

## Menyambungkan ke backend

Backend cukup menyediakan `GET /api/dashboard` yang mengembalikan JSON bertipe `Dashboard` (lihat `lib/types.ts`)
dan mengaktifkan CORS untuk `http://localhost:3000`.
