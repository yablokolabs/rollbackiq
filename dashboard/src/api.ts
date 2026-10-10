// The dashboard is a read-only view over the control-plane API, whose document
// is itself assembled from the committed evidence artifacts. Nothing here is
// synthesised on the client: every number shown on screen arrived from an
// artifact the pipeline or the Duo flow actually wrote.

export interface MetricWindow {
  release: string | null;
  environment: string | null;
  started_at: string | null;
  ended_at: string | null;
  request_count: number | null;
  error_count: number | null;
  error_rate: number | null;
  availability: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  mean_ms: number | null;
  max_ms: number | null;
  source: string | null;
}

export interface Detection {
  triggered: boolean;
  incident_id: string | null;
  breaches: string[];
  reasons: string[];
  confidence: number | null;
  confidence_note: string | null;
  p95_ratio: number | null;
  windows: MetricWindow[];
  proposal_hash: string | null;
}

export interface SafetyCheck {
  code: string;
  passed: boolean;
  detail: string;
}

export interface SafetyDecision {
  allowed: boolean;
  stage: string | null;
  detail: string | null;
  veto_codes: string[];
  checks: SafetyCheck[];
  proposal_hash: string | null;
}

export interface Approval {
  id: string | null;
  incident_id: string | null;
  proposal_hash: string | null;
  actor: string | null;
  decision: string | null;
  environment: string | null;
  created_at: string | null;
  expires_at: string | null;
  scope_note: string | null;
}

export interface DeployRecord {
  release: string | null;
  environment: string | null;
  image_digest: string | null;
  commit_sha: string | null;
  pipeline_id: string | null;
  fault_latency_ms: string | null;
  fault_error_rate: string | null;
  deployed_at: string | null;
}

export interface Verification {
  recovered: boolean | null;
  reasons: string[];
  samples: number | null;
  window_seconds: number | null;
  p95_ms: number | null;
  baseline_p95_ms: number | null;
  p95_ratio_vs_baseline: number | null;
  error_rate: number | null;
  independent: boolean | null;
  expected_release: string | null;
  observed_release: string | null;
  verified_at: string | null;
  after: MetricWindow | null;
}

export interface TimelineEvent {
  at: string;
  kind: string;
  title: string;
  detail: string | null;
  link: string | null;
}

export interface EvidenceLink {
  label: string;
  target: string;
  kind: string;
}

export interface PipelineJob {
  name: string;
  stage: string | null;
  status: string | null;
  duration_seconds: number | null;
  web_url: string | null;
}

export interface Pipeline {
  id: string | null;
  status: string | null;
  ref: string | null;
  sha: string | null;
  web_url: string | null;
  jobs: PipelineJob[];
}

export interface DuoMessage {
  type: string | null;
  truncated: boolean;
  text: string;
}

export interface DuoSession {
  session_id: string | null;
  url: string | null;
  status: string | null;
  human_status: string | null;
  agent_name: string | null;
  created_at: string | null;
  updated_at: string | null;
  trigger_surface: string | null;
  messages: DuoMessage[];
  report_note_id: string | null;
  report_excerpt: string | null;
  errors: unknown[];
}

export interface Incident {
  id: string;
  environment: string;
  status: string;
  detected_at: string | null;
  fault_nature: string;
  code_rollback_note: string;
  baseline: MetricWindow | null;
  detection: Detection | null;
  current_release: DeployRecord | null;
  target_release: DeployRecord | null;
  safety: SafetyDecision | null;
  approval: Approval | null;
  rollback_executed_at: string | null;
  idempotency_key: string | null;
  resolved_image_digest: string | null;
  verification: Verification | null;
  pipeline: Pipeline | null;
  duo: DuoSession | null;
  timeline: TimelineEvent[];
  evidence: EvidenceLink[];
  missing_artifacts: string[];
}

export interface IncidentSummary {
  id: string;
  environment: string;
  status: string;
  detected_at: string | null;
  target_release: string | null;
  recovered: boolean | null;
  independent: boolean | null;
  p95_ratio: number | null;
  duo_session_status: string | null;
}

async function getJSON<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${url} -> HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchIncidentList(): Promise<IncidentSummary[]> {
  return getJSON<IncidentSummary[]>("/api/incidents");
}

export async function fetchIncident(id: string): Promise<Incident> {
  return getJSON<Incident>(`/api/incidents/${encodeURIComponent(id)}`);
}

export function formatUTC(iso: string | null | undefined, withDate = false): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const time = date.toISOString().slice(11, 19) + " UTC";
  return withDate ? `${date.toISOString().slice(0, 10)} ${time}` : time;
}

export function shortDigest(digest: string | null | undefined): string {
  if (!digest) return "—";
  return digest.startsWith("sha256:") ? `${digest.slice(0, 7)}…${digest.slice(-6)}` : digest;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function fixed(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}

export function statusTone(status: string): string {
  switch (status) {
    case "recovered":
    case "FINISHED":
    case "success":
      return "bg-emerald-500/15 text-emerald-300 ring-emerald-400/30";
    case "unverified":
    case "RUNNING":
    case "manual":
      return "bg-amber-500/15 text-amber-300 ring-amber-400/30";
    case "escalated":
    case "FAILED":
    case "failed":
      return "bg-rose-500/15 text-rose-300 ring-rose-400/30";
    default:
      return "bg-slate-500/15 text-slate-300 ring-slate-400/30";
  }
}
