"use client";

import { useEffect, useState } from "react";
import { DoorOpen, Droplets, Thermometer, Trees } from "lucide-react";
import { getDashboard, isLive } from "@/lib/api";
import type { Dashboard as Data } from "@/lib/types";
import { fmt, fmt1, fmtTime } from "@/lib/status";
import Gauge from "./Gauge";
import RecommendationCard from "./RecommendationCard";
import StatTile from "./StatTile";
import CO2Chart from "./CO2Chart";
import EventList from "./EventList";

const REFRESH_MS = 5000;

export default function Dashboard() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const d = await getDashboard();
        if (alive) { setData(d); setError(null); }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Gagal memuat data");
      }
    };
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Udara kelas GD 525</h1>
          <p className="mt-1 text-muted">Prediksi CO₂ 15 menit ke depan dengan model GRU</p>
        </div>
        <div className="flex items-center gap-3 text-sm text-muted">
          <span className="inline-flex items-center gap-2 rounded-full bg-paper px-3 py-1.5">
            <span className={`size-2 rounded-full ${error ? "bg-high" : "bg-good live-dot"}`} />
            {error ? "Terputus" : isLive ? "Data langsung" : "Data simulasi"}
          </span>
          {data && <span>Diperbarui {fmtTime(data.updatedAt)} WIB</span>}
        </div>
      </header>

      {error && (
        <p role="alert" className="mt-4 rounded-2xl bg-[#f6d9d1] p-4 text-sm">
          {error}. Periksa apakah backend berjalan dan NEXT_PUBLIC_API_URL benar.
        </p>
      )}

      {!data ? (
        <p className="mt-16 text-center text-muted">Memuat data sensor…</p>
      ) : (
        <div className="mt-6 space-y-4">
          <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
            <Gauge current={data.current.co2} predicted={data.forecast[data.forecast.length - 1].co2} />
            <RecommendationCard rec={data.recommendation} />
          </div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile icon={Thermometer} label="Suhu dalam" value={`${fmt1(data.current.tempIn)} °C`}
              hint={`${fmt1(data.current.tempIn - data.current.tempOut)} °C lebih hangat dari luar`} />
            <StatTile icon={Droplets} label="Kelembapan dalam" value={`${fmt(data.current.humIn)}%`}
              hint="Dari sensor DHT22 dalam ruangan" />
            <StatTile icon={Trees} label="Suhu luar" value={`${fmt1(data.current.tempOut)} °C`}
              hint={`Kelembapan luar ${fmt(data.current.humOut)}%`} />
            <StatTile icon={DoorOpen} label="Okupansi" value={data.current.occupied ? "Ada orang" : "Kosong"}
              hint="Terdeteksi sensor PIR" />
          </div>

          <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
            <CO2Chart history={data.history} forecast={data.forecast} />
            <EventList events={data.events} />
          </div>
        </div>
      )}

      <footer className="mt-10 text-sm text-muted">
        Ambang utama 1.000 ppm. Rekomendasi ventilasi bersifat saran, bukan kontrol otomatis.
      </footer>
    </main>
  );
}
