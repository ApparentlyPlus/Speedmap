// the speed ramp, so a search dot and a street agree

// branded, they won't add together by accident
export type Mbps = number & { readonly unit: "Mbps" };
export type EurPerMonth = number & { readonly unit: "EUR/month" };

export const mbps = (n: number): Mbps => n as Mbps;
export const eur = (n: number): EurPerMonth => n as EurPerMonth;

export type Band = {
  readonly floor: Mbps;
  readonly colour: string;
  readonly name: string;
};

// fastest first, the first band a speed clears is its band
export const RAMP: readonly Band[] = [
  { floor: mbps(1000), colour: "#a78bfa", name: "1 Gbps" },
  { floor: mbps(500), colour: "#7b8cf5", name: "500 Mbps" },
  { floor: mbps(300), colour: "#4da3ff", name: "300 Mbps" },
  { floor: mbps(200), colour: "#45c8e0", name: "200 Mbps" },
  { floor: mbps(100), colour: "#ffc93c", name: "100 Mbps" },
  { floor: mbps(50), colour: "#ff8c42", name: "50 Mbps" },
  { floor: mbps(0), colour: "#f4523b", name: "24 Mbps" },
];

// reaches, no speed filed. Off the ramp or it goes near black
export const UNFILED = "#9fb3c8";

// nothing reaches, dark but not the slow red
export const UNSERVED = "#2a3038";

// every speed a street is retailed at (technology.sold_mbps, a test checks they match)
const RETAILED: readonly Mbps[] = [mbps(24), mbps(50), mbps(100), mbps(1000)];

export function bandsPainted(continuous: boolean): readonly Band[] {
  if (continuous) return RAMP;
  const reached = new Set(RETAILED.map((speed) => bandFor(speed)?.name));
  return RAMP.filter((band) => reached.has(band.name));
}

export function bandFor(speed: Mbps | null): Band | null {
  if (speed === null) return null;
  return RAMP.find((band) => speed >= band.floor) ?? null;
}

export function colourFor(speed: Mbps | null): string {
  return bandFor(speed)?.colour ?? UNFILED;
}

// white, five operators already own five hues
export const ACCENT = "#ffffff";

export const FAR = "#6366f1";

// fiber share 0..1, one hue getting lighter since hue already means speed
export const SHARE: readonly (readonly [number, string])[] = [
  [0, "#161d26"],
  [0.15, "#1c2f3f"],
  [0.35, "#22485c"],
  [0.6, "#2a6b7d"],
  [0.85, "#3f96a0"],
  [1, "#67c7c4"],
];
