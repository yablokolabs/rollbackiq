import { formatUTC, type Incident } from "../api";

const KIND_STYLES: Record<string, string> = {
  deploy: "bg-sky-400",
  baseline: "bg-emerald-400",
  window: "bg-slate-400",
  detection: "bg-rose-400",
  approval: "bg-amber-300",
  rollback: "bg-violet-400",
  verification: "bg-emerald-400",
  verdict: "bg-emerald-300",
  duo: "bg-fuchsia-400",
  "duo-report": "bg-fuchsia-300",
};

export default function Timeline({ incident }: { incident: Incident }) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
      <h2 className="text-sm font-medium text-slate-300">
        Incident timeline — detection to verified recovery, all timestamps UTC
      </h2>
      <ol className="mt-5 space-y-5">
        {incident.timeline.map((event) => (
          <li key={`${event.at}-${event.kind}-${event.title}`} className="relative pl-6">
            <span
              className={`absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full ${KIND_STYLES[event.kind] ?? "bg-slate-400"}`}
              aria-hidden="true"
            />
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <time className="tabular text-xs text-slate-400" dateTime={event.at}>
                {formatUTC(event.at)}
              </time>
              <span className="text-sm font-medium">{event.title}</span>
            </div>
            {event.detail && <p className="mt-1 max-w-3xl text-sm text-slate-400">{event.detail}</p>}
            {event.link && (
              <a
                className="mt-1 inline-block text-xs text-sky-300 underline decoration-dotted hover:text-sky-200"
                href={event.link}
                target="_blank"
                rel="noreferrer"
              >
                open record
              </a>
            )}
          </li>
        ))}
      </ol>
      <p className="mt-5 text-xs text-slate-500">
        Every entry maps to a timestamp inside an artifact under <code>evidence/</code>; approval wait
        is kept separate from detection and recovery time on purpose.
      </p>
    </section>
  );
}
