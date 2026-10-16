"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Tab = "progress" | "manifest" | "timeline" | "gaps" | "draft" | "bns" | "export";

// Single case-detail page with tabs, per docs/HACKATHON_PLAN.md's core journey
// (PRD §1.5). TODO(N): split into components/ once each tab has real content;
// this file is the scaffold so every screen exists and is routable from H1.
export default function CaseDetailPage({ params }: { params: { id: string } }) {
  const [tab, setTab] = useState<Tab>("progress");
  const [manifest, setManifest] = useState<any>(null);
  const [timeline, setTimeline] = useState<any>(null);
  const [gaps, setGaps] = useState<any>(null);
  const [draft, setDraft] = useState<any>(null);
  const [bns, setBns] = useState<any>(null);

  useEffect(() => {
    api.getManifest(params.id).then(setManifest);
    api.getTimeline(params.id).then(setTimeline);
    api.getGaps(params.id).then(setGaps);
    api.getDraft(params.id).then(setDraft);
    api.getBns(params.id).then(setBns);
  }, [params.id]);

  const tabs: Tab[] = ["progress", "manifest", "timeline", "gaps", "draft", "bns", "export"];

  return (
    <main className="mx-auto max-w-4xl p-8">
      <h1 className="mb-4 text-2xl font-semibold">Case {params.id}</h1>
      <nav className="mb-6 flex gap-2 border-b">
        {tabs.map((t) => (
          <button
            key={t}
            className={`px-3 py-2 ${tab === t ? "border-b-2 border-slate-900 font-medium" : "text-slate-500"}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </nav>

      {tab === "progress" && (
        <div className="text-slate-500">
          {/* TODO(N): POST /api/cases/{id}/runs then poll GET /api/runs/{run_id} every 1.5s,
              render each of the 6 steps' state (waiting/running/done/failed/skipped) */}
          Run progress — polling not yet wired.
        </div>
      )}

      {tab === "manifest" && (
        <ul className="space-y-2">
          {manifest?.files?.map((f: any) => (
            <li key={f.id} className="rounded border bg-white p-3">
              <div className="font-medium">{f.name}</div>
              <div className="text-sm text-slate-500">sha256: {f.sha256}</div>
              {f.screening && (
                <div className="mt-1 text-sm">
                  {f.screening.label} —{" "}
                  <span className="text-slate-400">{f.screening.limitation}</span>
                </div>
              )}
              {/* TODO(N): dedup badge when is_duplicate_of is set; metadata conflict line */}
            </li>
          ))}
        </ul>
      )}

      {tab === "timeline" && (
        <ul className="space-y-2">
          {/* TODO(N): replace with vis-timeline; click a source chip -> highlight the source file line */}
          {timeline?.events?.map((e: any) => (
            <li key={e.id} className="rounded border bg-white p-3">
              <div className="text-sm text-slate-500">{e.timestamp}</div>
              <div>{e.summary}</div>
            </li>
          ))}
        </ul>
      )}

      {tab === "gaps" && (
        <ul className="space-y-2">
          {gaps?.gaps?.map((g: any) => (
            <li key={g.id} className="rounded border bg-white p-3">
              <div>{g.question}</div>
              {/* TODO(N): PATCH /api/gaps/{id} with an answer or a dismiss reason;
                  re-fetch gaps after, since the backend re-runs the rules */}
              <div className="mt-1 text-sm text-slate-400">status: {g.status}</div>
            </li>
          ))}
        </ul>
      )}

      {tab === "draft" && (
        <div className="space-y-2">
          {draft?.sentences?.map((s: any, i: number) => (
            <p
              key={i}
              className={s.supported ? "cursor-pointer hover:bg-amber-50" : "bg-red-50 text-red-700"}
              title={s.supported ? `Sources: ${s.event_ids.join(", ")}` : "Unsupported — needs officer review"}
            >
              {s.sentence}
              {!s.supported && <span className="ml-2 text-xs font-medium">Unsupported — needs officer review</span>}
            </p>
          ))}
          {/* TODO(N): click a sentence -> highlight the cited source in the manifest/timeline */}
        </div>
      )}

      {tab === "bns" && (
        <ul className="space-y-2">
          {bns?.suggestions?.map((b: any) => (
            <li key={b.id} className="rounded border bg-white p-3">
              <div className="font-medium">{b.section} — {b.title}</div>
              <ul className="ml-4 list-disc text-sm text-slate-500">
                {b.ingredients.map((ing: string, i: number) => <li key={i}>{ing}</li>)}
              </ul>
              <div className="mt-1 text-xs text-slate-400">Advisory: SHO decides</div>
              {/* TODO(N): accept/reject buttons -> POST /api/bns/{id}/decision, SHO role only */}
            </li>
          ))}
        </ul>
      )}

      {tab === "export" && (
        <div className="text-slate-500">
          {/* TODO(N): SHO approve button -> POST /api/cases/{id}/approve, then
              POST /api/cases/{id}/export; show the QR code and §63 draft link */}
          Export — requires SHO approval first.
        </div>
      )}
    </main>
  );
}
