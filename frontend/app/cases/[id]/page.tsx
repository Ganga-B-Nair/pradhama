"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import RequireUser from "@/components/RequireUser";
import { StatusTag } from "@/components/case/bits";
import { CaseProvider, Src } from "@/components/case/ctx";
import SourceModal from "@/components/case/SourceModal";
import Complainant from "@/components/case/Complainant";
import Evidence from "@/components/case/Evidence";
import Narration from "@/components/case/Narration";
import Analysis from "@/components/case/Analysis";
import Manifest from "@/components/case/Manifest";
import Timeline from "@/components/case/Timeline";
import Gaps from "@/components/case/Gaps";
import Draft from "@/components/case/Draft";
import Bns from "@/components/case/Bns";
import Referrals from "@/components/case/Referrals";
import Approval from "@/components/case/Approval";
import Export from "@/components/case/Export";
import Audit from "@/components/case/Audit";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { cap, fmt } from "@/lib/util";

const ROLE_TABS: Record<string, string[]> = {
  officer: ["complainant", "evidence", "narration", "analysis", "manifest", "timeline", "gaps", "draft", "bns", "referrals", "approval"],
  sho: ["complainant", "evidence", "narration", "analysis", "manifest", "timeline", "gaps", "draft", "bns", "referrals", "approval", "export", "audit"],
};
const REVIEW = ["manifest", "timeline", "gaps", "draft", "bns", "referrals"];
const VIEWS: Record<string, () => JSX.Element> = {
  complainant: () => <Complainant />, evidence: Evidence, narration: Narration, analysis: Analysis, manifest: Manifest,
  timeline: Timeline, gaps: Gaps, draft: Draft, bns: Bns, referrals: Referrals, approval: Approval, export: Export, audit: Audit,
};

function Workspace() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const { user, L } = useSession();
  const [c, setC] = useState<any>(null);
  const [err, setErr] = useState("");
  const [segments, setSegments] = useState<any[]>([]);
  const [src, setSrc] = useState<Src | null>(null);

  const reload = useCallback(async () => {
    try { setC(await api.get(`/cases/${id}`)); } catch (e: any) { setErr(e.message); }
  }, [id]);
  const reloadNarration = useCallback(async () => {
    const n = await api.get(`/cases/${id}/narration`).catch(() => null);
    setSegments(n?.segments || []);
  }, [id]);
  useEffect(() => { reload(); reloadNarration(); }, [reload, reloadNarration]);

  if (err) return <main>{err}</main>;
  if (!c || !user) return <main className="muted">Loading…</main>;

  const tabs = ROLE_TABS[user.role];
  const def = !c.complainant.consent_at ? "complainant" : c.analysis.done ? "manifest" : c.files_count ? "narration" : "evidence";
  const want = search.get("tab") || def;
  const tab = tabs.includes(want) ? want : tabs[0];
  const setTab = (t: string) => { router.replace(`/cases/${id}?tab=${t}`, { scroll: true }); window.scrollTo(0, 0); };
  const locked = ["approved", "exported"].includes(c.status);
  const canEdit = !locked && !c.analysis.running;
  const isSho = user.role === "sho";

  const done: Record<string, boolean> = {
    complainant: !!c.complainant.consent_at, evidence: c.files_count > 0, narration: c.narration_segments > 0,
    analysis: !!c.analysis.done, approval: locked, export: c.exports_count > 0,
  };
  const btn = (t: string) => (
    <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{L(t)}{done[t] ? " ✓" : ""}</button>
  );
  const steps: JSX.Element[] = [];
  let n = 0;
  for (const t of ["complainant", "evidence", "narration", "analysis", "REVIEW", "approval", "export"]) {
    if (t === "REVIEW") {
      const rt = REVIEW.filter((x) => tabs.includes(x));
      if (n++) steps.push(<span key="sep-r" className="sep">›</span>);
      steps.push(<span key="g-r" className="group">{n}. Review</span>, ...rt.map(btn));
      continue;
    }
    if (!tabs.includes(t)) continue;
    if (n++) steps.push(<span key={`sep-${t}`} className="sep">›</span>);
    steps.push(<span key={`g-${t}`} className="group">{n}.</span>, btn(t));
  }
  if (tabs.includes("audit")) steps.push(<span key="sp" style={{ marginLeft: "auto" }} />, btn("audit"));

  const View = VIEWS[tab];
  return (
    <CaseProvider value={{ c, reload, tab, setTab, canEdit, isSho, locked, segments, reloadNarration, openSrc: setSrc }}>
      <div className="casehead">
        <b>{c.ref}</b><StatusTag s={c.status} /><span>{c.complainant.name}</span>
        <span className="muted">Language: {c.complainant.language}</span>
        <span>Open gaps: <b>{c.open_gaps}</b></span><span className="muted">{c.files_count} files</span>
      </div>
      <div className="steps">{steps}</div>
      <main>
        {locked && <div className="note okbar">{cap(c.status)} on {fmt(c.approval.at)} by {c.approval.by} (draft v{c.approval.version}). The case is read-only.{isSho ? " Reopen it from Approval if a change is needed." : ""}</div>}
        {c.analysis.stale && !locked && !c.analysis.running && <div className="note warnbar">Evidence or narration changed after the last analysis. <button className="link" onClick={() => setTab("analysis")}>Run analysis again</button></div>}
        {c.sent_back && !locked && c.status === "review" && <div className="note warnbar">Sent back by {c.sent_back.by} on {fmt(c.sent_back.at)}: “{c.sent_back.comment}”</div>}
        <View key={tab} />
      </main>
      {src && <SourceModal src={src} onClose={() => setSrc(null)} />}
    </CaseProvider>
  );
}

export default function Page() {
  return <RequireUser bare><Suspense fallback={<main className="muted">Loading…</main>}><Workspace /></Suspense></RequireUser>;
}
