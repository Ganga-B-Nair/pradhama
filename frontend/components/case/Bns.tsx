"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmt, money } from "@/lib/util";
import { Chips } from "./bits";
import { useCase } from "./ctx";

export default function Bns() {
  const { c, isSho, locked } = useCase();
  const [list, setList] = useState<any[] | null>(null);
  const [events, setEvents] = useState<Record<string, any>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get(`/cases/${c.id}/bns`).then((r) => setList(r.suggestions));
    api.get(`/cases/${c.id}/timeline`).then((r) => setEvents(Object.fromEntries(r.events.map((e: any) => [e.id, e]))));
  }, [c.id]);
  if (!list) return <><h2>BNS section review</h2><p className="muted">Loading…</p></>;
  if (!list.length) return <><h2>BNS section review</h2><p className="muted">No suggestions yet. Run analysis first.</p></>;

  const can = isSho && !locked;
  const decided = list.filter((b) => b.decision).length;
  async function decide(id: string, decision: string | null) {
    try { setList((await api.post(`/cases/${c.id}/bns/${id}/decision`, { decision, note: notes[id] || "" })).suggestions); } catch (e: any) { setErr(e.message); }
  }
  return (
    <>
      <h2>BNS section review</h2>
      <p className="muted">{decided} of {list.length} decided. {isSho ? "Approval stays blocked until every suggestion is accepted or rejected." : "Only the SHO decides these suggestions."}</p>
      <div className="note warnbar small">Advisory — sections to be verified. Section numbers and ingredients come from a local fixture ({list[0].source}) and must be checked by a legal mentor; the SHO decides.</div>
      <p className="err">{err}</p>
      {list.map((b) => (
        <div className="box" key={b.id}>
          <div className="row" style={{ justifyContent: "space-between" }}><b>{b.section} · {b.title}</b><span className="tag">Advisory: SHO decides</span></div>
          <p><span className="muted">Summary:</span> {b.summary}</p>
          <table className="small">
            <thead><tr><th style={{ width: "34%" }}>Required ingredient</th><th>Supporting evidence</th></tr></thead>
            <tbody>
              {b.ingredients.map((ing: any) => (
                <tr key={ing.text}>
                  <td>{ing.text}</td>
                  <td>{ing.event_ids.length ? <ul style={{ margin: 0, paddingLeft: 18 }}>{ing.event_ids.map((id: string) => {
                    const e = events[id];
                    return e ? <li key={id}>{fmt(e.at, e.prec === "exact")}: {e.action}{e.amount ? ` (${money(e.amount)})` : ""} <Chips src={e.src} /></li> : null;
                  })}</ul> : <span className="warn">No supporting evidence found yet</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {b.decision ? (
            <p><span className={`tag ${b.decision === "Accepted" ? "ok" : "bad"}`}>{b.decision}</span> by {b.by}, {fmt(b.at)}{b.note ? ` · “${b.note}”` : ""} {can && <button className="link small" onClick={() => decide(b.id, null)}>Change</button>}</p>
          ) : can ? (
            <div className="row" style={{ marginTop: 8 }}>
              <input placeholder="Note (optional)" style={{ flex: 1 }} value={notes[b.id] || ""} onChange={(e) => setNotes({ ...notes, [b.id]: e.target.value })} />
              <button onClick={() => decide(b.id, "Accepted")}>Accept</button><button onClick={() => decide(b.id, "Rejected")}>Reject</button>
            </div>
          ) : <p className="muted small">Pending SHO decision.</p>}
        </div>
      ))}
    </>
  );
}
