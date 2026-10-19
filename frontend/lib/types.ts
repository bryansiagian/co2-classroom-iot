export type Level = "good" | "watch" | "high" | "critical";

export type Point = { t: number; co2: number };

export type Recommendation = {
  action: "none" | "watch" | "flush";
  minutes: number; // lama ventilasi (menit), 0 jika tidak perlu
  reason: string;
};

export type DashboardEvent = { t: number; text: string; level: Level };

export type Dashboard = {
  room: string;
  updatedAt: number; // epoch ms
  current: {
    co2: number;
    tempIn: number;
    humIn: number;
    tempOut: number;
    humOut: number;
    occupied: boolean; // dari PIR
  };
  history: Point[]; // 1 menit sekali, urut naik
  forecast: Point[]; // t+1 .. t+15 menit
  recommendation: Recommendation;
  events: DashboardEvent[]; // terbaru di indeks 0
};
