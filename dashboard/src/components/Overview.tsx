import type { ReactNode } from "react";
import { fixed, formatUTC, pct, shortDigest, type Incident, type MetricWindow } from "../api";

function p95Bar(window: MetricWindow | null, max: number, tone: string) {
  if (!window?.p95_ms) return null;
  const width = Math.max(6, Math.round((window.p95_ms / max) * 100));
  return (
    <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800" role="img"
      aria-label={`p95 ${fixed(window.p95_ms)} milliseconds`}>
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <h3 className="text-xs font-medium uppercase tracking-wider text-slate-400">{title}</h3>
      <div className="mt-3 space-y-1.5 text-sm">{children}</div>
    </section>
  );
}

export default function Overview({ incident }: { incident: Incident }) {
  const baseline = incident.baseline;
  const windows = incident.detection?.windows ?? [];
  const after = incident.verification?.after ?? null;
  const all = [baseline, ...windows, after].filter((w): w is MetricWindow => Boolean(w));
  const max = Math.max(...all.map((w) => w.p95_ms ?? 0), 1);

  const rows: { label: string; window: MetricWindow | null; tone: string; note: string }[] = [
    { label: "Baseline v1 (healthy)", window: baseline, tone: "bg-emerald-400", note: "pre-regression" },
    { label: "Faulty v2 · window 1", window: windows[0] ?? null, tone: "bg-rose-400", note: "detection window" },
    { label: "Faulty v2 · window 2", window: windows[1] ?? null, tone: "bg-rose-400", note: "thresholds breached here" },
    { label: "Post-rollback v1", window: after, tone: "bg-emerald-400", note: "independent verification window" },
  ];

  const safety = incident.safety;
  const checks = safety?.checks ?? [];
  const passed = checks.filter((check) => check.passed).length;
  const verification = incident.verification;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card title="Current release">
          <p className="text-lg font-semibold text-rose-300">{incident.current_release?.release ?? "—"}</p>
          <p className="text-slate-400">
            digest <span className="tabular">{shortDigest(incident.current_release?.image_digest)}</span>
          </p>
          <p className="text-slate-400">
            fault inputs: latency {incident.current_release?.fault_latency_ms ?? "—"} ms · error rate{" "}
            {incident.current_release?.fault_error_rate ?? "—"}
          </p>
          <p className="text-slate-500">deployed {formatUTC(incident.current_release?.deployed_at)}</p>
        </Card>

        <Card title="Healthy baseline">
          <p className="text-lg font-semibold text-emerald-300">
            p95 {fixed(baseline?.p95_ms)} ms
          </p>
          <p className="text-slate-400">
            {baseline?.request_count ?? "—"} requests · {baseline?.error_count ?? "—"} errors
          </p>
          <p className="text-slate-500">captured {formatUTC(baseline?.started_at)}</p>
        </Card>

        <Card title="Detection">
          <div className="flex flex-wrap gap-1.5">
            {(incident.detection?.breaches ?? []).map((breach) => (
              <span key={breach} className="rounded-full bg-rose-500/15 px-2.5 py-0.5 text-xs text-rose-300 ring-1 ring-rose-400/30">
                {breach}
              </span>
            ))}
          </div>
          <p className="tabular text-slate-400">
            window 2 p95 ratio {fixed(incident.detection?.p95_ratio, 2)}× baseline
          </p>
          {incident.detection?.confidence != null && (
            <p className="text-slate-500">
              confidence {incident.detection.confidence.toFixed(2)} — {incident.detection.confidence_note}
            </p>
          )}
        </Card>

        <Card title="Verification verdict">
          <p className={`text-lg font-semibold ${verification?.recovered ? "text-emerald-300" : "text-rose-300"}`}>
            {verification?.recovered == null ? "—" : verification.recovered ? "Recovered" : "Not recovered"}
          </p>
          <p className="tabular text-slate-400">
            p95 {verification?.p95_ratio_vs_baseline != null ? `${verification.p95_ratio_vs_baseline.toFixed(3)}×` : "—"} baseline
          </p>
          <p className="text-slate-400">
            {verification?.samples ?? "—"} samples over {fixed(verification?.window_seconds, 2)} s
          </p>
          <p className="text-slate-500">
            independent: {verification?.independent == null ? "—" : String(verification.independent)}
          </p>
        </Card>
      </div>

      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-sm font-medium text-slate-300">Latency across the incident (real HTTP probes)</h2>
        <ul className="mt-4 space-y-4">
          {rows.map((row) => (
            <li key={row.label}>
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                <span className="font-medium">{row.label}</span>
                <span className="tabular text-slate-400">
                  {row.window?.p95_ms != null ? `p95 ${fixed(row.window.p95_ms)} ms` : "—"}
                  {row.window?.error_rate != null ? ` · errors ${pct(row.window.error_rate)}` : ""}
                  {row.window?.request_count != null ? ` · n=${row.window.request_count}` : ""}
                </span>
              </div>
              <div className="mt-1.5">
                {p95Bar(row.window, max, row.tone)}
              </div>
              <p className="mt-1 text-xs text-slate-500">{row.note}</p>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-slate-500">
          Bars scale to the largest p95 in the set ({fixed(max)} ms). Values come from{" "}
          <code>evidence/gitlab-ci-lifecycle-artifacts/</code>; the probe source is recorded on each window.
        </p>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Safety gate">
          <p className="text-lg font-semibold">
            {passed}/{checks.length || "—"} checks passed
          </p>
          <p className="text-slate-400">
            veto codes: {safety?.veto_codes?.length ? safety.veto_codes.join(", ") : "none"}
          </p>
          <p className="tabular text-slate-500">proposal {safety?.proposal_hash ?? "—"}</p>
        </Card>

        <Card title="Duo investigation">
          <p className="text-lg font-semibold">{incident.duo?.agent_name ?? "—"}</p>
          <p className="text-slate-400">
            session {incident.duo?.session_id ?? "—"} · {incident.duo?.status ?? "—"}
          </p>
          <p className="text-slate-500">
            {incident.duo?.report_excerpt
              ? "posted an audit note on the incident issue"
              : "no report note captured"}
          </p>
        </Card>
      </div>
    </div>
  );
}
