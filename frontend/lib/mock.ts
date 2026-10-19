import type { Dashboard, DashboardEvent, Point, Recommendation } from "./types";
import { THRESHOLDS } from "./status";

// Data simulasi: satu siklus kelas 150 menit (kelas terisi -> flush -> pulih).
// Dipakai selama backend belum tersedia. Ganti dengan API asli lewat NEXT_PUBLIC_API_URL.
const CYCLE = 150;

function noise(minute: number) {
  const x = Math.sin(minute * 12.9898) * 43758.5453;
  return (x - Math.floor(x) - 0.5) * 24;
}

function co2At(minute: number) {
  const m = ((minute % CYCLE) + CYCLE) % CYCLE;
  let v: number;
  if (m < 100) {
    v = 520 + 800 * (1 - Math.exp(-m / 60));
  } else if (m < 108) {
    const v100 = 520 + 800 * (1 - Math.exp(-100 / 60));
    v = 560 + (v100 - 560) * Math.exp(-(m - 100) / 3);
  } else {
    v = 560 - (m - 108) * (40 / 42);
  }
  return Math.round(v + noise(minute));
}

function isOccupied(minute: number) {
  return ((minute % CYCLE) + CYCLE) % CYCLE < 100;
}

function predict(history: Point[]): Point[] {
  const last = history[history.length - 1];
  const ref = history[history.length - 6];
  const slope = (last.co2 - ref.co2) / 5;
  const out: Point[] = [];
  let acc = 0;
  for (let k = 1; k <= 15; k++) {
    acc += Math.pow(0.96, k);
    out.push({ t: last.t + k * 60_000, co2: Math.round(Math.max(400, last.co2 + slope * acc)) });
  }
  return out;
}

function recommend(now: number, forecast: Point[]): Recommendation {
  const peak = Math.max(...forecast.map((p) => p.co2));
  const at15 = forecast[forecast.length - 1].co2;
  if (peak >= THRESHOLDS.high) {
    const minutes = peak >= THRESHOLDS.critical ? 5 : peak >= 1150 ? 4 : 3;
    return {
      action: "flush",
      minutes,
      reason: `CO₂ diprediksi mencapai ${Math.round(at15)} ppm dalam 15 menit. Buka jendela dan pintu sekarang agar tidak melewati 1.000 ppm.`,
    };
  }
  if (peak >= THRESHOLDS.watch) {
    return {
      action: "watch",
      minutes: 0,
      reason: `CO₂ diprediksi naik ke ${Math.round(at15)} ppm. Belum perlu ventilasi, tetapi bersiap jika tren berlanjut.`,
    };
  }
  return {
    action: "none",
    minutes: 0,
    reason: "CO₂ diprediksi tetap di bawah 800 ppm dalam 15 menit ke depan.",
  };
}

function buildEvents(history: Point[]): DashboardEvent[] {
  const events: DashboardEvent[] = [];
  for (let i = 1; i < history.length; i++) {
    const a = history[i - 1].co2;
    const b = history[i].co2;
    const t = history[i].t;
    if (a < THRESHOLDS.high && b >= THRESHOLDS.high) {
      events.push({ t, text: "CO₂ melewati 1.000 ppm", level: "high" });
    } else if (a < THRESHOLDS.watch && b >= THRESHOLDS.watch) {
      events.push({ t, text: "CO₂ melewati 800 ppm", level: "watch" });
    }
    const dropping = (j: number) => j >= 3 && history[j - 3].co2 - history[j].co2 > 120;
    if (dropping(i) && !dropping(i - 1)) {
      events.push({ t, text: "CO₂ turun cepat, ventilasi diduga dibuka", level: "good" });
    }
  }
  return events.reverse().slice(0, 5);
}

export function buildMockDashboard(now: number): Dashboard {
  const nowMin = Math.floor(now / 60_000);
  const history: Point[] = [];
  for (let i = 359; i >= 0; i--) {
    history.push({ t: (nowMin - i) * 60_000, co2: co2At(nowMin - i) });
  }
  const forecast = predict(history);
  const co2 = history[history.length - 1].co2;
  const tempIn = 27.4 + ((co2 - 520) / 800) * 1.6;
  return {
    room: "GD 525",
    updatedAt: now,
    current: {
      co2,
      tempIn: Math.round(tempIn * 10) / 10,
      humIn: 62,
      tempOut: 24.8,
      humOut: 78,
      occupied: isOccupied(nowMin),
    },
    history,
    forecast,
    recommendation: recommend(now, forecast),
    events: buildEvents(history),
  };
}
