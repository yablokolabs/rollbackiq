import { fixed, statusTone, type Incident } from "../api";

export default function Report({ incident }: { incident: Incident }) {
  const pipeline = incident.pipeline;

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-sm font-medium text-slate-300">Evidence</h2>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {incident.evidence.map((link) => (
            <li key={`${link.kind}-${link.target}`} className="rounded-lg bg-slate-950/60 px-3 py-2 text-sm">
              {link.target.startsWith("http") ? (
                <a className="text-sky-300 underline decoration-dotted hover:text-sky-200" href={link.target} target="_blank" rel="noreferrer">
                  {link.label} ↗
                </a>
              ) : (
                <>
                  <span className="text-slate-300">{link.label}</span>{" "}
                  <code className="text-xs text-slate-500">{link.target}</code>
                </>
              )}
            </li>
          ))}
        </ul>
      </section>

      {pipeline && (
        <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <header className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium text-slate-300">
              Pipeline {pipeline.id} <span className="text-slate-500">({pipeline.status ?? "—"})</span>
            </h2>
            {pipeline.web_url && (
              <a className="text-xs text-sky-300 underline decoration-dotted" href={pipeline.web_url} target="_blank" rel="noreferrer">
                open pipeline ↗
              </a>
            )}
          </header>
          <table className="mt-4 w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-slate-500">
                <th className="pb-2 pr-4 font-medium">Job</th>
                <th className="pb-2 pr-4 font-medium">Stage</th>
                <th className="pb-2 pr-4 font-medium">Status</th>
                <th className="pb-2 font-medium">Duration</th>
              </tr>
            </thead>
            <tbody className="text-slate-300">
              {pipeline.jobs.map((job) => (
                <tr key={`${job.name}-${job.web_url ?? ""}`} className="border-t border-slate-800/70">
                  <td className="py-1.5 pr-4">
                    {job.web_url ? (
                      <a className="hover:text-sky-200" href={job.web_url} target="_blank" rel="noreferrer">
                        {job.name}
                      </a>
                    ) : (
                      job.name
                    )}
                  </td>
                  <td className="py-1.5 pr-4 text-slate-400">{job.stage ?? "—"}</td>
                  <td className="py-1.5 pr-4">
                    <span className={`rounded-full px-2 py-0.5 text-xs ring-1 ${statusTone(job.status ?? "")}`}>
                      {job.status ?? "—"}
                    </span>
                  </td>
                  <td className="tabular py-1.5 text-slate-400">
                    {job.duration_seconds != null ? `${fixed(job.duration_seconds, 1)} s` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-sm font-medium text-slate-300">What this report does not claim</h2>
        <ul className="mt-3 space-y-3 text-sm">
          <li className="text-slate-300">{incident.fault_nature}</li>
          <li className="text-amber-200/90">{incident.code_rollback_note}</li>
          <li className="text-slate-400">
            Whether v2's HTTP 500 responses left any write-side data inconsistency cannot be
            determined from the available evidence; the Duo flow's audit escalated exactly this
            question rather than assuming an answer.
          </li>
          {incident.missing_artifacts.length > 0 && (
            <li className="text-amber-200/90">
              Missing artifacts: {incident.missing_artifacts.join(", ")}
            </li>
          )}
        </ul>
        <dl className="mt-5 grid gap-3 border-t border-slate-800 pt-4 text-xs text-slate-400 sm:grid-cols-3">
          <div>
            <dt className="uppercase tracking-wider text-slate-500">Incident</dt>
            <dd className="tabular">{incident.id}</dd>
          </div>
          <div>
            <dt className="uppercase tracking-wider text-slate-500">Idempotency key</dt>
            <dd className="tabular break-all">{incident.idempotency_key ?? "—"}</dd>
          </div>
          <div>
            <dt className="uppercase tracking-wider text-slate-500">Resolved digest</dt>
            <dd className="tabular break-all">{incident.resolved_image_digest ?? "—"}</dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-slate-500">
          Generated from committed evidence artifacts. Timestamps are UTC; the console reads only —
          it cannot approve, execute or verify anything.
        </p>
      </section>
    </div>
  );
}
