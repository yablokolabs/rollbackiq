import { formatUTC, type Incident } from "../api";

export default function Investigation({ incident }: { incident: Incident }) {
  const duo = incident.duo;
  const detection = incident.detection;

  return (
    <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-slate-300">GitLab Duo custom flow</h2>
            <p className="mt-1 text-xs text-slate-500">{duo?.trigger_surface ?? "trigger surface not recorded"}</p>
          </div>
          {duo?.url && (
            <a
              className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs text-sky-300 ring-1 ring-slate-700 hover:bg-slate-700"
              href={duo.url}
              target="_blank"
              rel="noreferrer"
            >
              open agent session ↗
            </a>
          )}
        </header>

        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs uppercase tracking-wider text-slate-500">Session</dt>
            <dd className="tabular">{duo?.session_id ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wider text-slate-500">Status</dt>
            <dd>{duo?.status ?? "—"} ({duo?.human_status ?? "—"})</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wider text-slate-500">Started</dt>
            <dd className="tabular">{formatUTC(duo?.created_at, true)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wider text-slate-500">Last update</dt>
            <dd className="tabular">{formatUTC(duo?.updated_at, true)}</dd>
          </div>
        </dl>

        {duo?.report_excerpt && (
          <blockquote className="mt-5 rounded-lg border border-fuchsia-500/30 bg-fuchsia-500/5 p-4">
            <p className="text-xs uppercase tracking-wider text-fuchsia-300">
              Audit note the flow posted on the issue
              {duo.report_note_id ? ` (note ${duo.report_note_id})` : ""}
            </p>
            <p className="mt-2 whitespace-pre-wrap text-sm text-slate-200">{duo.report_excerpt}</p>
            {duo.report_note_id && (
              <a
                className="mt-2 inline-block text-xs text-sky-300 underline decoration-dotted"
                href={`https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43178176/showcase/-/work_items/2#note_${duo.report_note_id}`}
                target="_blank"
                rel="noreferrer"
              >
                read the full note on the issue ↗
              </a>
            )}
          </blockquote>
        )}

        <h3 className="mt-6 text-xs font-medium uppercase tracking-wider text-slate-400">
          Captured session messages
        </h3>
        <ul className="mt-3 space-y-3">
          {(duo?.messages ?? []).slice(0, 8).map((message, index) => (
            <li key={index} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <p className="text-xs text-slate-500">
                {message.type ?? "unknown"} · {message.truncated ? "truncated in capture" : "complete"}
              </p>
              <p className="mt-1 whitespace-pre-wrap text-sm text-slate-300">{message.text}</p>
            </li>
          ))}
        </ul>
        {duo && duo.messages.length === 0 && (
          <p className="mt-3 text-sm text-slate-500">
            The session record captured no messages; the platform's own session link above is the
            source of truth.
          </p>
        )}
      </section>

      <section className="space-y-6">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <h2 className="text-sm font-medium text-slate-300">Why the detector fired</h2>
          <ul className="mt-3 space-y-2 text-sm text-slate-300">
            {(detection?.reasons ?? []).map((reason) => (
              <li key={reason} className="rounded-lg bg-slate-950/60 px-3 py-2">
                {reason}
              </li>
            ))}
            {(detection?.reasons ?? []).length === 0 && <li className="text-slate-500">No reasons recorded.</li>}
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            Confidence is the detector's margin-and-sample indicator, not a probability —
            the artifact says so in its own words.
          </p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <h2 className="text-sm font-medium text-slate-300">Nature of the regression</h2>
          <p className="mt-3 text-sm text-slate-300">{incident.fault_nature}</p>
          <p className="mt-3 text-sm text-amber-200/90">{incident.code_rollback_note}</p>
          <p className="mt-3 text-xs text-slate-500">
            This is why the flow's audit recommended HOLD on the data-integrity question even though
            the deployment itself was restored: the two questions are separate.
          </p>
        </div>
      </section>
    </div>
  );
}
