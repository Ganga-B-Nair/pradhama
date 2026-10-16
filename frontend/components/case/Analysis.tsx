"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmt } from "@/lib/util";
import { useCase } from "./ctx";

const STEP_TAB: Record<string, string> = { triage: "manifest", metadata: "manifest", asr: "narration", timeline: "timeline", gaps: "gaps", draft: "draft" };
const STEPS = [["triage", "Content Triage"], ["metadata", "Metadata"], ["asr", "Speech-to-text"], ["timeline", "Timeline"], ["gaps", "Gap Hunter"], ["draft", "Draft builder"]];
const DET = ["triage", "metadata", "gaps"];

export default function Analysis() {
  const { c, canEdit, setTab, reload } = useCase();
  const [run, setRun] = useState<any>(null);
  const [err, setErr] = useState("");
  const running = !!c.analysis.running || (run && ["queued", "running"].includes(run.state));

  useEffect(() => { api.get(`/cases/${c.id}/runs/latest`).then(setRun); }, [c.id]);
  // Poll every 1.5 s while a run is in flight (plan §5); no request waits on the pipeline.
  useEffect(() => {
    if (!run || !["queued", "running"].includes(run.state)) return;
    const t = setInterval(async () => {
      const r = await api.get(`/runs/${run.id}`);
      setRun(r);
      if (!["queued", "running"].includes(r.state)) reload();
    }, 1500);
    return () => clearInterval(t);
  }, [run?.id, run?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  const ready = c.complainant.consent_at && (c.files_count || c.narration_status);
  async function start(startAt?: string) {
    setErr("");
    try {
      const { run_id } = await api.post(`/cases/${c.id}/runs`, startAt ? { start_at: startAt } : {});
      setRun(await api.get(`/runs/${run_id}`));
      reload();
    } catch (e: any) { setErr(e.message); }
  }
  async function skip(step: string) { setRun(await api.post(`/runs/${run.id}/skip/${step}`)); }

  const steps = run?.steps || STEPS.map(([name, label]) => ({ name, label, state: "waiting", note: null }));
  return (
    <>
      <h2>Analysis</h2>
      <p className="muted">Runs in the background, one case at a time: deterministic steps first, then speech-to-text in its own process, then the language model, then Gap Hunter. A failed step never blocks the case: the officer can retry it or continue by hand.</p>
      {c.analysis.ran_at && <p>Last run finished {fmt(c.analysis.ran_at)}{run?.engine ? <span className="muted small"> · orchestrated by {run.engine}</span> : null}.</p>}
      {canEdit && !running && <>
        <div className="row"><button className="primary" disabled={!ready} onClick={() => start()}>{c.analysis.done ? "Run analysis again" : "Run analysis"}</button></div>
        {!ready && <p className="muted small">Add evidence or narration first.</p>}
      </>}
      {c.narration_status && ["pending", "transcribing"].includes(c.narration_status) && !running && <p className="muted small">The narration is still being transcribed; the analysis will wait for it.</p>}
      <p className="err">{err}</p>
      <table style={{ marginTop: 10 }}>
        <thead><tr><th>Step</th><th>State</th><th>Result</th><th></th></tr></thead>
        <tbody>
          {steps.map((s: any) => {
            const cls = s.state === "done" ? "ok" : s.state === "failed" ? "bad" : s.state === "running" ? "warn" : "muted";
            return (
              <tr key={s.name}>
                <td>{s.label}{DET.includes(s.name) ? <span className="muted small"> (deterministic)</span> : null}</td>
                <td className={cls}>{s.state.charAt(0).toUpperCase() + s.state.slice(1)}{s.state === "running" ? "…" : ""}</td>
                <td>{s.note}</td>
                <td className="row">
                  {s.state === "done" && STEP_TAB[s.name] && <button className="small" onClick={() => setTab(STEP_TAB[s.name])}>Open</button>}
                  {s.state === "failed" && canEdit && !running && <>
                    <button className="small" onClick={() => start(s.name)}>Retry</button>
                    <button className="small" onClick={() => skip(s.name)}>Continue without it</button>
                  </>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
