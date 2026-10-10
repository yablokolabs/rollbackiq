import { useCallback, useEffect, useState } from "react";
import { fetchIncident, fetchIncidentList, formatUTC, statusTone, type Incident } from "./api";
import Overview from "./components/Overview";
import Timeline from "./components/Timeline";
import Investigation from "./components/Investigation";
import Approval from "./components/Approval";
import Verification from "./components/Verification";
import Report from "./components/Report";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "timeline", label: "Timeline" },
  { id: "investigation", label: "Investigation" },
  { id: "approval", label: "Approval centre" },
  { id: "verification", label: "Verification" },
  { id: "report", label: "Incident report" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [incident, setIncident] = useState<Incident | null>(null);
  const [tab, setTab] = useState<TabId>("overview");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const summaries = await fetchIncidentList();
      if (summaries.length === 0) {
        setError("The API returned no incidents.");
        return;
      }
      setIncident(await fetchIncident(summaries[0].id));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <main className="mx-auto flex h-full max-w-3xl flex-col justify-center gap-4 p-8">
        <h1 className="text-xl font-semibold">RollbackIQ console</h1>
        <p className="text-rose-300">
          The control-plane API could not be reached ({error}). Start it with{" "}
          <code className="rounded bg-slate-800 px-1.5 py-0.5">
            uvicorn app.api.incident_api:app --app-dir backend --port 8000
          </code>
          .
        </p>
      </main>
    );
  }

  if (!incident) {
    return (
      <main className="flex h-full items-center justify-center text-slate-400">
        Loading the incident record …
      </main>
    );
  }

  const verification = incident.verification;

  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col gap-6 p-6 lg:p-8">
      <header className="flex flex-col gap-4 border-b border-slate-800 pb-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              RollbackIQ <span className="text-slate-500">· incident console</span>
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Detect · Decide · Recover — every figure below comes from a committed evidence
              artifact the pipeline or the Duo flow wrote.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded-full px-3 py-1 ring-1 ${statusTone(incident.status)}`}>
              incident {incident.status}
            </span>
            <span className="rounded-full bg-slate-800 px-3 py-1 ring-1 ring-slate-700">
              {incident.environment}
            </span>
            {incident.duo && (
              <span className={`rounded-full px-3 py-1 ring-1 ${statusTone(incident.duo.status ?? "")}`}>
                Duo flow {incident.duo.status}
              </span>
            )}
            <span className="tabular rounded-full bg-slate-800 px-3 py-1 ring-1 ring-slate-700">
              detected {formatUTC(incident.detected_at)}
            </span>
            {verification?.p95_ratio_vs_baseline != null && (
              <span className="tabular rounded-full bg-slate-800 px-3 py-1 ring-1 ring-slate-700">
                p95 {verification.p95_ratio_vs_baseline.toFixed(3)}× baseline
              </span>
            )}
          </div>
        </div>

        {incident.missing_artifacts.length > 0 && (
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
            {incident.missing_artifacts.length} expected artifact(s) were not present, so the
            fields they carry are shown as “—”: {incident.missing_artifacts.join(", ")}
          </p>
        )}
      </header>

      <nav aria-label="Incident views" className="flex flex-wrap gap-1">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            onClick={() => setTab(entry.id)}
            aria-current={tab === entry.id ? "page" : undefined}
            className={
              "rounded-lg px-3.5 py-2 text-sm transition " +
              (tab === entry.id
                ? "bg-slate-100 font-medium text-slate-900"
                : "text-slate-300 hover:bg-slate-800")
            }
          >
            {entry.label}
          </button>
        ))}
      </nav>

      <main className="flex-1">
        {tab === "overview" && <Overview incident={incident} />}
        {tab === "timeline" && <Timeline incident={incident} />}
        {tab === "investigation" && <Investigation incident={incident} />}
        {tab === "approval" && <Approval incident={incident} />}
        {tab === "verification" && <Verification incident={incident} />}
        {tab === "report" && <Report incident={incident} />}
      </main>

      <footer className="border-t border-slate-800 pt-4 text-xs text-slate-500">
        Read-only view over <code>evidence/</code> · {incident.fault_nature}
      </footer>
    </div>
  );
}
