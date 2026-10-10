import { fixed, formatUTC, pct, type Incident, type MetricWindow } from "../api";

function Comparison({ window, max, tone }: { window: MetricWindow | null; max: number; tone: string }) {
  if (window?.p95_ms == null) return <div className="h-2.5 rounded-full bg-slate-800" />;
  const width = Math.max(5, Math.round((window.p95_ms / max) * 100));
  return (
    <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}

export default function Verification({ incident }: { incident: Incident }) {
  const verification = incident.verification;
  const faulty = incident.detection?.windows?.[1] ?? incident.detection?.windows?.[0] ?? null;
  const after = verification?.after ?? null;
  const baseline = incident.baseline;
  const max = Math.max(faulty?.p95_ms ?? 0, after?.p95_ms ?? 0, baseline?.p95_ms ?? 0, 1);

  const recovered = verification?.recovered;

  return (
    <div className="space-y-6">
      <section
        className={`rounded-xl border p-5 ${
          recovered ? "border-emerald-500/30 bg-emerald-500/10" : "border-rose-500/30 bg-rose-500/10"
        }`}
      >
        <h2 className="text-lg font-semibold">
          {recovered == null ? "No verdict recorded" : recovered ? "Recovery verified" : "Recovery not established"}
        </h2>
        <p className="mt-1 text-sm text-slate-300">
          {verification?.independent
            ? "The verification window started after the rollback executed, so it is independent of the data that triggered detection."
            : "Independence could not be established from the recorded timestamps."}
        </p>
        {verification?.reasons && verification.reasons.length > 0 && (
          <ul className="mt-3 list-inside list-disc text-sm text-rose-200">
            {verification.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid gap-4 md:grid-cols-4">
        {[
          { label: "Samples", value: verification?.samples ?? "—" },
          { label: "Window", value: verification?.window_seconds != null ? `${fixed(verification.window_seconds, 2)} s` : "—" },
          { label: "Post-rollback p95", value: verification?.p95_ms != null ? `${fixed(verification.p95_ms)} ms` : "—" },
          { label: "Error rate", value: verification?.error_rate != null ? pct(verification.error_rate) : "—" },
        ].map((item) => (
          <section key={item.label} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h3 className="text-xs uppercase tracking-wider text-slate-500">{item.label}</h3>
            <p className="tabular mt-2 text-xl font-semibold">{item.value}</p>
          </section>
        ))}
      </div>

      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-sm font-medium text-slate-300">Faulty → restored, measured</h2>
        <ul className="mt-4 space-y-4 text-sm">
          <li>
            <div className="flex justify-between">
              <span>Faulty v2 (trigger window)</span>
              <span className="tabular text-slate-400">
                {faulty?.p95_ms != null ? `p95 ${fixed(faulty.p95_ms)} ms · errors ${pct(faulty.error_rate)}` : "—"}
              </span>
            </div>
            <div className="mt-1.5"><Comparison window={faulty} max={max} tone="bg-rose-400" /></div>
          </li>
          <li>
            <div className="flex justify-between">
              <span>Post-rollback v1 (independent)</span>
              <span className="tabular text-slate-400">
                {after?.p95_ms != null ? `p95 ${fixed(after.p95_ms)} ms · errors ${pct(after.error_rate)}` : "—"}
              </span>
            </div>
            <div className="mt-1.5"><Comparison window={after} max={max} tone="bg-emerald-400" /></div>
          </li>
          <li>
            <div className="flex justify-between">
              <span>Healthy baseline</span>
              <span className="tabular text-slate-400">
                {baseline?.p95_ms != null ? `p95 ${fixed(baseline.p95_ms)} ms · errors ${pct(baseline.error_rate)}` : "—"}
              </span>
            </div>
            <div className="mt-1.5"><Comparison window={baseline} max={max} tone="bg-emerald-300" /></div>
          </li>
        </ul>
        <dl className="mt-5 grid gap-3 border-t border-slate-800 pt-4 text-xs text-slate-400 sm:grid-cols-3">
          <div>
            <dt className="uppercase tracking-wider text-slate-500">Rollback executed</dt>
            <dd className="tabular">{formatUTC(incident.rollback_executed_at, true)}</dd>
          </div>
          <div>
            <dt className="uppercase tracking-wider text-slate-500">Verification window started</dt>
            <dd className="tabular">{formatUTC(after?.started_at, true)}</dd>
          </div>
          <div>
            <dt className="uppercase tracking-wider text-slate-500">Verified at</dt>
            <dd className="tabular">{formatUTC(verification?.verified_at, true)}</dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-slate-500">
          A rollback job exiting zero proves the job ran, not that the service recovered. This view
          is built from the verifier's own window and refuses the claim when the evidence is thin —
          a thin window was refused exactly this way earlier in the project and the refusal is kept
          as evidence.
        </p>
      </section>
    </div>
  );
}
