import type { Dashboard } from "./types";
import { buildMockDashboard } from "./mock";

const API = process.env.NEXT_PUBLIC_API_URL;

export const isLive = Boolean(API);

// Jika NEXT_PUBLIC_API_URL kosong -> data simulasi.
// Jika diisi -> GET {API}/api/dashboard harus mengembalikan JSON bertipe Dashboard (lihat lib/types.ts).
export async function getDashboard(): Promise<Dashboard> {
  if (!API) return buildMockDashboard(Date.now());
  const res = await fetch(`${API}/api/dashboard`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API mengembalikan status ${res.status}`);
  return res.json();
}
