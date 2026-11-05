// Types mirror api/elderleaf/schemas.py (the contract with the backend).

/** API address baked in at build time (NEXT_PUBLIC_API_URL). */
export const DEFAULT_API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const SERVER_KEY = "elderleaf-server";

/** The API address in use: a server set on this device (Settings in the Android app) wins over the build-time one. */
export function apiUrl(): string {
  if (typeof window !== "undefined") {
    try {
      const custom = localStorage.getItem(SERVER_KEY);
      if (custom) return custom;
    } catch {}
  }
  return DEFAULT_API_URL;
}

/** Point this device at another API (e.g. the Modal URL, or a laptop on the same Wi-Fi). `null` goes back to the default. */
export function setServerUrl(url: string | null) {
  try {
    const clean = url?.trim().replace(/\/+$/, "");
    if (!clean || clean === DEFAULT_API_URL) localStorage.removeItem(SERVER_KEY);
    else localStorage.setItem(SERVER_KEY, /^https?:\/\//.test(clean) ? clean : `https://${clean}`);
  } catch {}
}

/** True inside the Android app (Capacitor injects window.Capacitor). */
export function isNativeApp(): boolean {
  if (typeof window === "undefined") return false;
  const cap = (window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
  return Boolean(cap?.isNativePlatform?.());
}

export type Status = "pending" | "running" | "done" | "failed";

export interface TraceStep {
  step: number;
  tool: string;
  label: string;
  input: string | null;
  result: string | null;
  status: "running" | "done" | "failed" | "skipped";
  image_url: string | null;
}

export interface MaskOut {
  id: string;
  class: "crop" | "weed" | "lesion" | "scale";
  prompt: string;
  score: number | null;
  area_px: number;
  box: number[];
  polygons: number[][][];
  /** crop id of a crop mask in a mixed bed (null when plants could not be told apart) */
  crop?: string | null;
}

export interface MetricValue {
  value: number | null;
  unit: string;
  how: string;
  mask_ids: string[];
}

export interface ContextItem {
  metric: string;
  status: "typical" | "attention" | "info";
  text: string;
  badge: string | null;
}

export interface Summary {
  text: string;
  next_step: string | null;
  source: "agent" | "template";
  attempts: number;
  validator_issues: string[];
  error: string | null;
}

/** Water need. Analyses carry the report agent's estimate (no `available` field, null when there is no weather);
 * GET /plots/{id}/water answers with `available` and a `reason` when it can't estimate. */
export interface Irrigation {
  available?: boolean;
  text?: string;
  source?: string;
  kc_stage?: number | null;
  reason?: string;
  date?: string;
  et0_mm?: number;
  rain_mm?: number;
  stage?: string;
  kc?: number;
  kd?: number;
  kc_adj?: number;
  canopy_cover_pct?: number | null;
  liters_per_m2?: number;
  area_m2?: number | null;
  plot_total_liters?: number | null;
  how?: string;
  rain_note?: string | null;
}

/** The report agent's combined report (Markdown) with its headline and next steps. */
export interface Report {
  headline: string;
  next_steps: string[];
  markdown: string;
  written_by: "agent" | "template";
  validator: { passed: boolean; attempts: number; errors: string[] };
  looked_closer: string | null;
}

export interface AnalysisResult {
  analysis_id: string;
  plot_id: string;
  captured_at: string;
  days_after_planting: number | null;
  segmenter: string;
  image: { width: number; height: number };
  image_quality: {
    blur: number;
    brightness: number;
    clipped_pct: number;
    sharp: boolean;
    exposure: string;
    exposure_ok: boolean;
    level: "good" | "low";
  };
  masks: MaskOut[];
  metrics: {
    plant_count: MetricValue;
    canopy_cover_pct: MetricValue;
    weed_share_pct: MetricValue;
    lesion_share_pct: MetricValue | null;
    mean_plant_area: MetricValue;
    /** mixed beds: count and cover per crop id */
    by_crop?: Record<string, { label: string; plant_count: number; canopy_cover_pct: number; mask_ids: string[] }> | null;
  };
  scale: { found: boolean; mask_id: string | null; px_per_cm2: number | null; note: string };
  health: {
    assessed: boolean;
    signs: { type: string; likelihood: string; evidence_mask_ids: string[]; description: string; share_pct?: number | null }[];
    detection_confidence: number | null;
    consult_agronomist: boolean;
    consult_reasons: string[];
    /** yellowing / browning / leaf_spots as % of crop area (measured in code) */
    measures?: Record<string, number>;
    summary?: string | null;
  };
  context: ContextItem[];
  comparison: {
    previous_analysis_id: string;
    previous_captured_at: string;
    days_between: number;
    deltas: Record<string, number>;
    growth_rate: Record<string, number>;
    summary: string;
  } | null;
  crop_info?: {
    stage: string;
    stage_start_day: number;
    stage_end_day: number;
    kc: number;
    cover_typical_pct: [number, number];
    source: string;
  } | null;
  irrigation: Irrigation | null;
  /** the report agent's combined report (also at GET /analyses/{id}/report.md) */
  report?: Report | null;
  /** the report agent's short summary and next step (older analyses may only have this) */
  summary?: Summary | null;
  notes_since_previous?: { date: string; kind: string; text: string }[];
  run_stats: {
    /** agent = ranked words for one crop; scan = mixed bed, one phrase per kind of plant; fixed = no LLM */
    strategy: "agent" | "scan" | "fixed";
    scene: string | null;
    sam_calls: number;
    sam_cost_usd: number;
    total_cost_usd: number | null;
    wall_time_s: number;
    chosen: Record<string, { prompt: string; rank: number | "fallback" }>;
    llm: { provider: string; model: string } | null;
  } | null;
  agent_trace: TraceStep[];
}

export interface AnalysisOut {
  id: string;
  plot_id: string;
  captured_at: string;
  status: Status;
  error: string | null;
  image_url: string;
  overlay_url: string | null;
  trace: TraceStep[];
  result: AnalysisResult | null;
}

export interface AnalysisSummary {
  id: string;
  captured_at: string;
  status: Status;
  image_url: string;
  summary: string | null;
  plant_count: number | null;
  canopy_cover_pct: number | null;
  weed_share_pct: number | null;
  lesion_share_pct: number | null;
  mean_plant_area: number | null;
  mean_plant_area_unit: string | null;
  attention: string[];
}

export interface Note {
  id: string;
  kind: string;
  date: string;
  text: string;
}

export interface Plot {
  id: string;
  name: string;
  crop: string;
  crop_label: string;
  /** more than one crop in the same photo: the agent lists every kind of plant (scan mode) */
  mixed: boolean;
  other_crops: string[];
  other_crop_labels: string[];
  planted_on: string | null;
  days_after_planting: number | null;
  area_m2: number | null;
  row_spacing_cm: number | null;
  plant_spacing_cm: number | null;
  lat: number | null;
  lon: number | null;
  is_demo: boolean;
  latest: AnalysisSummary | null;
  deltas: Record<string, number> | null;
  attention: string[];
}

export interface PlotDetail extends Plot {
  analyses: AnalysisSummary[];
  notes: Note[];
}

export interface CompareSide {
  analysis_id: string;
  captured_at: string;
  days_after_planting: number | null;
  image_url: string;
  overlay_url: string | null;
}

/** GET /plots/{id}/compare: the earlier photo is "before". The summary is written by the report agent (or a template). */
export interface CompareOut {
  plot_id: string;
  before: CompareSide;
  after: CompareSide;
  days_between: number;
  rows: { metric: string; label: string; unit: string | null; before: number | null; after: number | null; change: number | null; per_day: number | null }[];
  by_crop: { crop: string; label: string; before: number | null; after: number | null; change: number | null }[];
  notes: Note[];
  summary: string;
  next_step: string | null;
  written_by: "agent" | "template";
  validator: { passed: boolean; attempts: number; errors: string[] };
}

export type Experience = "just_started" | "few_seasons" | "experienced";

export const EXPERIENCE: { id: Experience; label: string; hint: string }[] = [
  { id: "just_started", label: "Just started", hint: "First season" },
  { id: "few_seasons", label: "A season or two", hint: "Some harvests behind you" },
  { id: "experienced", label: "Experienced", hint: "Years in the soil" },
];

export interface User {
  id: string;
  email: string;
  name: string;
  garden: string | null;
  experience: Experience;
  created_at: string;
}

export interface Me extends User {
  stats: { plots: number; photos: number; notes: number; plants_counted: number; first_measured: string | null };
}

export interface AuthOut {
  token: string;
  user: User;
  claimed_plots: number;
}

export interface Health {
  ok: boolean;
  sam_configured: boolean;
  segmenter: string;
  llm_configured: boolean;
  llm_provider: string;
}

// ------------------------------------------------------------------ device id (no login)

export function deviceId(): string {
  try {
    let id = localStorage.getItem("elderleaf-device");
    if (!id) {
      id = "d_" + crypto.randomUUID().replace(/-/g, "").slice(0, 20);
      localStorage.setItem("elderleaf-device", id);
    }
    return id;
  } catch {
    return "d_anonymous";
  }
}

// ------------------------------------------------------------------ account (optional sign-in)

const TOKEN_KEY = "elderleaf-token";
/** Fired when someone signs in or out, so lists and the header reload. */
export const AUTH_CHANGED = "elderleaf:auth-changed";

export function authToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {}
  window.dispatchEvent(new Event(AUTH_CHANGED));
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Device-Id", deviceId());
  const token = authToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let resp: Response;
  try {
    resp = await fetch(apiUrl() + path, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Can't reach the ElderLeaf server. Check your connection and try again.");
  }
  if (!resp.ok) {
    let message = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {}
    throw new ApiError(resp.status, message);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

export const api = {
  health: () => call<Health>("/health"),
  signUp: async (body: { email: string; password: string; name: string; garden?: string | null; experience: Experience }) => {
    const out = await call<AuthOut>("/auth/signup", { method: "POST", body: JSON.stringify(body) });
    setAuthToken(out.token);
    return out;
  },
  logIn: async (email: string, password: string) => {
    const out = await call<AuthOut>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    setAuthToken(out.token);
    return out;
  },
  logOut: async () => {
    try {
      await call<void>("/auth/logout", { method: "POST" });
    } catch {
      // signing out on this device works even when the server can't be reached
    } finally {
      setAuthToken(null);
    }
  },
  me: () => call<Me>("/me"),
  updateMe: (body: { name?: string; garden?: string | null; experience?: Experience }) => call<Me>("/me", { method: "PATCH", body: JSON.stringify(body) }),
  crops: () => call<{ id: string; label: string }[]>("/crops"),
  plots: () => call<Plot[]>("/plots"),
  plot: (id: string) => call<PlotDetail>(`/plots/${id}`),
  createPlot: (body: Record<string, unknown>) => call<Plot>("/plots", { method: "POST", body: JSON.stringify(body) }),
  deletePlot: (id: string) => call<void>(`/plots/${id}`, { method: "DELETE" }),
  analysis: (id: string) => call<AnalysisOut>(`/analyses/${id}`),
  upload: (plotId: string, file: Blob, capturedAt?: string, filename?: string) => {
    const form = new FormData();
    form.append("file", file, filename || "plot.jpg");
    if (capturedAt) form.append("captured_at", capturedAt);
    return call<AnalysisOut>(`/plots/${plotId}/analyses`, { method: "POST", body: form });
  },
  rerun: (id: string) => call<AnalysisOut>(`/analyses/${id}/rerun`, { method: "POST" }),
  addNote: (plotId: string, body: { kind: string; date: string; text: string }) =>
    call<Note>(`/plots/${plotId}/notes`, { method: "POST", body: JSON.stringify(body) }),
  water: (plotId: string) => call<Irrigation & { based_on_analysis_id: string | null }>(`/plots/${plotId}/water`),
  compare: (plotId: string, a: string, b: string) => call<CompareOut>(`/plots/${plotId}/compare?a=${a}&b=${b}`),
  csvUrl: (plotId: string) => `${apiUrl()}/plots/${plotId}/export.csv`,
  analysisJsonUrl: (id: string) => `${apiUrl()}/analyses/${id}`,
  reportUrl: (id: string) => `${apiUrl()}/analyses/${id}/report.md`,
};

// ------------------------------------------------------------------ formatting

export function fmt(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  return Number.isInteger(v) ? String(v) : v.toFixed(digits);
}

export function fmtDate(iso: string): string {
  const d = new Date(iso + (iso.length === 10 ? "T12:00:00" : ""));
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function today(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

// Mask colors match the metric colors (crop = plants, weed = weeds, lesion = leaf spots); the A4 sheet is neutral.
export const CLASS_COLORS: Record<string, string> = {
  crop: "#1f9d55",
  weed: "#e8590c",
  lesion: "#7c4dcc",
  scale: "#8e8e96",
};
