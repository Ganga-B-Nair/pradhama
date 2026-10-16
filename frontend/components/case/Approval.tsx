"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmt, toast } from "@/lib/util";
import { useCase } from "./ctx";

export default function Approval() {
  const { c, isSho, locked, reload, setTab } = useCase();
  const [ck, setCk] = useState<any>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { api.get(`/cases/${c.id}/approval`).then(setCk); }, [c.id, c.status]);

  async function act(path: string, body?: any, after?: () => void) {
    setErr("");
    try { await api.post(`/cases/${c.id}/${path}`, body); setText(""); await reload(); setCk(await api.get(`/cases/${c.id}/approval`)); after?.(); }
    catch (e: any) { setErr(e.message); }
  }

  if (locked) return (
    <>
      <h2>Approval</h2>
      <p className="ok">Approved by {c.approval.by} on {fmt(c.approval.at)}. Draft v{c.approval.version} is locked.</p>
      {isSho && <>
        <h3>Reopen</h3>
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Reason for reopening (required)" />
        <p className="err">{err}</p>
        <button className="danger" onClick={() => text.trim() ? act("reopen", { text }) : setErr("A reason is required.")}>Reopen case</button>
      </>}
    </>
  );
  if (!ck) return <><h2>Approval</h2><p className="muted">Loading…</p></>;
  return (
    <>
      <h2>Approval</h2>
      <ul className="check">{ck.items.map(([t, v]: [string, boolean]) => <li key={t}><span className={v ? "ok" : "bad"}>{v ? "✓" : "✗"}</span> {t}</li>)}</ul>
      {ck.high.length > 0 && <>
        <h3>Open High-severity gaps</h3>
        {ck.high.map((g: any) => (
          <label key={g.id} className="row" style={{ margin: "4px 0" }}>
            <input type="checkbox" checked={!!c.approval.acks?.[g.id]} disabled={!isSho} onChange={(e) => act("approval/ack", { gap_id: g.id, value: e.target.checked })} />
            <span>I acknowledge this is unresolved: {g.q}</span>
          </label>
        ))}
      </>}
      <p className="err">{err}</p>
      {isSho ? <>
        <p style={{ marginTop: 12 }}>
          <button className="primary" disabled={!ck.ok || c.analysis.running} onClick={() => { if (confirm(`Approve draft v${ck.draft_version}? The case becomes read-only.`)) act("approve", {}, () => setTab("export")); }}>Approve draft v{ck.draft_version}</button>{" "}
          {!ck.ok && <span className="muted small">Complete the checklist to enable approval.</span>}
        </p>
        <h3>Send back to the writer</h3>
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Comment for the writer (required)" />
        <button onClick={() => text.trim() ? act("send-back", { text }, () => toast("Sent back to the writer")) : setErr("A comment is required.")}>Send back</button>
      </> : <p className="muted">The SHO reviews this checklist and approves the case. The officer files; the SHO approves.</p>}
    </>
  );
}
