import { formatUTC, type Incident } from "../api";

export default function Approval({ incident }: { incident: Incident }) {
  const approval = incident.approval;
  const safety = incident.safety;
  const checks = safety?.checks ?? [];

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-sm font-medium text-slate-300">Approval record</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-slate-400">Actor</dt>
            <dd className="font-medium">{approval?.actor ?? "—"}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-slate-400">Decision</dt>
            <dd className="font-medium">{approval?.decision ?? "—"}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-slate-400">Environment</dt>
            <dd>{approval?.environment ?? "—"}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-slate-400">Created</dt>
            <dd className="tabular">{formatUTC(approval?.created_at, true)}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-slate-400">Expires</dt>
            <dd className="tabular">{formatUTC(approval?.expires_at, true)}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Scoped to proposal</dt>
            <dd className="tabular mt-1 break-all">{approval?.proposal_hash ?? "—"}</dd>
          </div>
          {approval?.scope_note && (
            <div>
              <dt className="text-slate-400">Recorded how</dt>
              <dd className="mt-1 text-amber-200/90">{approval.scope_note}</dd>
            </div>
          )}
        </dl>
        <p className="mt-5 border-t border-slate-800 pt-4 text-xs text-slate-500">
          Approval is a human act. Execute authority lives in the pipeline's safety gate, which
          refuses any proposal whose approval does not match the exact proposal hash, environment
          and validity window — including any approval naming an automation identity.
        </p>
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <header className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-medium text-slate-300">Safety gate checks</h2>
          <p className="text-xs text-slate-400">
            {checks.filter((c) => c.passed).length}/{checks.length} passed · veto codes:{" "}
            {safety?.veto_codes?.length ? safety.veto_codes.join(", ") : "none"}
          </p>
        </header>
        <ul className="mt-4 grid gap-1.5 text-sm sm:grid-cols-2">
          {checks.map((check) => (
            <li
              key={check.code}
              className="flex items-start gap-2 rounded-lg bg-slate-950/60 px-3 py-2"
              title={check.detail}
            >
              <span
                className={`mt-0.5 inline-block h-2 w-2 flex-none rounded-full ${check.passed ? "bg-emerald-400" : "bg-rose-400"}`}
                aria-label={check.passed ? "passed" : "failed"}
              />
              <div>
                <p className="tabular text-xs text-slate-300">{check.code}</p>
                <p className="text-xs text-slate-500">{check.detail}</p>
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-slate-500">
          Fail closed: any failing check vetoes execution and the pipeline stops. The gate ran
          against the real proposed change before the rollback job was allowed to deploy.
        </p>
      </section>
    </div>
  );
}
