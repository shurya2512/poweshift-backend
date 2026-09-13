const API_URL = process.env.NEXT_PUBLIC_POWESHIFT_API_URL ?? 'http://localhost:8000';

export interface DiagnosticTrack {
  event_name: string;
  status: 'diagnostic_only' | 'unavailable';
  summary: string;
  mode: 'qualifying' | 'race';
  profiles: string[];
}

export interface DiagnosticCatalog {
  status: 'diagnostic_only';
  physicsAdmission: false;
  qualifying: DiagnosticTrack[];
  race: DiagnosticTrack[];
}

export type RunLifecycleStatus = 'pending' | 'running' | 'completed' | 'stopped' | 'failed';

export interface RunStatus {
  run_id: string;
  status: RunLifecycleStatus;
  recommendation_count: number;
  error: string | null;
}

export interface RuntimeRecommendation {
  run_id: string;
  request_id: string;
  sequence: number;
  intent: string;
  deployment_fraction: number;
  requested_power_w: number | null;
  reachable_power_w: number | null;
  evidence_status: 'retrospective_inference' | 'unsupported_fallback';
  binding_reasons: string[];
  created_monotonic_ns: number;
  expires_monotonic_ns: number;
  memory_version: number;
  policy_id: string;
  energy_bundle_id: string;
  continuous_profile_id: string;
  physics_id: string;
  rules_id: string;
  pit_manifest_id: string;
  route_id: string;
  scenario_id: string;
  news_prior_ids: string[];
  retrospective: boolean;
}

export interface RunReport {
  run_id: string;
  status: RunLifecycleStatus;
  partition: string;
  source_id: string;
  source_sha256: string;
  target_id: string;
  checkpoint_id: string;
  recommendation_count: number;
  fallback_count: number;
  recommendations_sha256: string;
  policy_id: string;
  energy_bundle_id: string;
  continuous_profile_id: string;
  physics_id: string;
  rules_id: string;
  pit_manifest_id: string;
  route_id: string;
  scenario_id: string;
  limitations: string[];
}

export interface LiveObservation {
  sequence: number;
  observed_at_s: number;
  values: number[];
  feature_mask: boolean[];
  action_mask: boolean[];
  deployment_available: boolean;
  news_prior_ids: string[];
}

export interface LiveRecommendation {
  decision_sequence: number;
  source_sequence: number;
  source_observed_at_s: number;
  input_hz: number;
  decision_hz: number;
  held_source_frame: boolean;
  partition: string;
  recommendation: RuntimeRecommendation;
}

async function readJson(path: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) throw new Error(`Backend returned ${response.status}`);
  return response.json() as Promise<Record<string, unknown>>;
}

// Reads the FastAPI `{"detail": "..."}` error body, if present.
async function readErrorDetail(response: Response): Promise<string | undefined> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === 'string' ? body.detail : undefined;
  } catch {
    return undefined;
  }
}

// A run result endpoint that is too early to have a result yet.
async function readResultOrNull<T>(response: Response, label: string): Promise<T | null> {
  if (response.status === 425) return null;
  if (!response.ok) throw new Error(`${label} returned ${response.status}`);
  return response.json() as Promise<T>;
}

export function normalizeDiagnosticTracks(
  value: unknown,
  mode: 'qualifying' | 'race',
): DiagnosticTrack[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== 'object' || item === null) return [];
    const row = item as Record<string, unknown>;
    if (typeof row.event_name !== 'string' || typeof row.summary !== 'string') return [];
    const status = row.status === 'unavailable' ? 'unavailable' : 'diagnostic_only';
    const profiles = Array.isArray(row.profiles) ? row.profiles.map(String) : [];
    return [{ event_name: row.event_name, summary: row.summary, status, mode, profiles }];
  });
}

export async function fetchDiagnosticCatalog(): Promise<DiagnosticCatalog> {
  const root = await readJson('/diagnostics/reports');
  const qualifyingPath = String(root.qualifying_index ?? 'qualifying/index.json');
  const racePath = String(root.race_index ?? 'race/index.json');
  const [qualifying, race] = await Promise.all([
    readJson(`/diagnostics/reports/${qualifyingPath}`),
    readJson(`/diagnostics/reports/${racePath}`),
  ]);
  return {
    status: 'diagnostic_only',
    physicsAdmission: false,
    qualifying: normalizeDiagnosticTracks(qualifying.tracks, 'qualifying'),
    race: normalizeDiagnosticTracks(race.tracks, 'race'),
  };
}

export async function fetchDiagnosticReport<T>(path: string): Promise<T> {
  return readJson(`/diagnostics/reports/${path}`) as Promise<T>;
}

export async function fetchRunStatus(runId: string): Promise<RunStatus> {
  return readJson(`/runs/${encodeURIComponent(runId)}`) as unknown as Promise<RunStatus>;
}

export async function controlRun(runId: string, command: 'pause' | 'resume' | 'stop'): Promise<void> {
  const response = await fetch(`${API_URL}/runs/${encodeURIComponent(runId)}/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command }),
  });
  if (!response.ok) throw new Error(`Run control returned ${response.status}`);
}

// Returns null while the run has not produced a recommendation yet.
export async function fetchLatestRecommendation(runId: string): Promise<RuntimeRecommendation | null> {
  const response = await fetch(`${API_URL}/runs/${encodeURIComponent(runId)}/recommendation`);
  return readResultOrNull<RuntimeRecommendation>(response, 'Recommendation fetch');
}

// Returns null while the run has not produced a report yet.
export async function fetchRunReport(runId: string): Promise<RunReport | null> {
  const response = await fetch(`${API_URL}/runs/${encodeURIComponent(runId)}/report`);
  return readResultOrNull<RunReport>(response, 'Report fetch');
}

function websocketUrl(path: string, search?: string): string {
  const url = new URL(API_URL);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = path;
  if (search !== undefined) url.search = search;
  return url.toString();
}

export async function startRegisteredRun(runId: string): Promise<void> {
  // Check first: an already-live run resolves here and skips the POST entirely,
  // avoiding a console-visible 409 for the common case.
  try {
    await fetchRunStatus(runId);
    return;
  } catch {
    // Unknown run id (404) — fall through to start it.
  }

  const response = await fetch(`${API_URL}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId }),
  });
  if (response.ok) return;
  if (response.status !== 409) throw new Error(`Run start returned ${response.status}`);

  // 409 means either the run is already live, or a stale output directory blocks this id.
  // Supervisor run state is in memory only, so ask it which case this is.
  const detail = await readErrorDetail(response);
  try {
    await fetchRunStatus(runId);
  } catch {
    const reason = detail ? ` (${detail})` : '';
    throw new Error(
      `Run "${runId}" cannot be started: its output already exists from a previous session, so the ` +
        `supervisor no longer recognizes this run id and it cannot be restarted under it${reason}.`,
    );
  }
}

export function streamRegisteredRun(
  runId: string,
  onRecommendation: (frame: RuntimeRecommendation) => void,
  onError: () => void,
  afterSequence?: number,
): () => void {
  const search = afterSequence === undefined ? undefined : `after_sequence=${afterSequence}`;
  const socket = new WebSocket(websocketUrl(`/runs/${encodeURIComponent(runId)}/stream`, search));
  socket.onmessage = (event) => onRecommendation(JSON.parse(event.data) as RuntimeRecommendation);
  socket.onerror = onError;
  return () => socket.close();
}

export function openLivePolicy(
  runId: string,
  onRecommendation: (frame: LiveRecommendation) => void,
  onError: () => void,
): { send: (observation: LiveObservation) => void; close: () => void } {
  const socket = new WebSocket(websocketUrl(`/runs/${encodeURIComponent(runId)}/live`));
  const pending: LiveObservation[] = [];
  socket.onopen = () => {
    for (const observation of pending.splice(0)) socket.send(JSON.stringify(observation));
  };
  socket.onmessage = (event) => onRecommendation(JSON.parse(event.data) as LiveRecommendation);
  socket.onerror = onError;
  return {
    send: (observation) => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(observation));
      else pending.push(observation);
    },
    close: () => socket.close(),
  };
}
