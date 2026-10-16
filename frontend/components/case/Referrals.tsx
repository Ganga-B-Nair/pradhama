"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmt, short } from "@/lib/util";
import { useCase } from "./ctx";

export default function Referrals() {
  const { c, isSho, locked, reload } = useCase();
  const [r, setR] = useState<any>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [add, setAdd] = useState({ file: "", reason: "" });
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get(`/cases/${c.id}/referrals`).then(setR);
    api.get(`/cases/${c.id}/manifest`).then((m) => setFiles(m.files));
  }, [c.id]);
  if (!r) return <><h2>Forensic referrals</h2><p className="muted">Loading…</p></>;

  const can = isSho && !locked;
  const F = (id: string) => files.find((f) => f.ev_id === id);
  const avail = files.filter((f) => !r.items.some((x: any) => x.file === f.ev_id));
  async function op(body: any) {
    setErr("");
    try { setR(await api.post(`/cases/${c.id}/referrals`, body)); reload(); } catch (e: any) { setErr(e.message); }
  }
  function remove(i: number) {
    const why = prompt("Reason for removing this file from the referral list (required):");
    if (why === null) return;
    if (!why.trim()) return alert("A reason is required.");
    op({ op: "remove", index: i, reason: why });
  }
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Forensic referrals</h2>
        <a className="linkbtn" style={{ textDecoration: "none", opacity: r.items.length ? 1 : 0.45, pointerEvents: r.items.length ? "auto" : "none" }} href={`/api/cases/${c.id}/referrals.csv`}>Download referral sheet</a>
      </div>
      <p className="muted">Ranked list of files to send to the forensic lab. Visible to officers only, and never printed on the complainant&apos;s copy.</p>
      <div className="note small">{r.limitation}</div>
      <table>
        <thead><tr><th>Rank</th><th>File</th><th>Reason</th><th>Confidence</th><th>SHA-256</th><th></th></tr></thead>
        <tbody>
          {r.items.length ? r.items.map((x: any, i: number) => (
            <tr key={x.file}>
              <td>{i + 1}</td><td>{x.file} · {F(x.file)?.name}</td>
              <td>{x.reason}{x.by !== "TRACE (machine)" && <span className="small muted"> (added by {x.by})</span>}</td>
              <td>{x.conf ?? "—"}</td><td className="mono">{short(F(x.file)?.sha256)}</td>
              <td>{can && <>
                <button className="small" disabled={!i} onClick={() => op({ op: "move", index: i, delta: -1 })}>↑</button>
                <button className="small" disabled={i === r.items.length - 1} onClick={() => op({ op: "move", index: i, delta: 1 })}>↓</button>
                <button className="small danger" onClick={() => remove(i)}>Remove</button>
              </>}</td>
            </tr>
          )) : <tr><td colSpan={6} className="muted">No files referred.</td></tr>}
        </tbody>
      </table>
      {r.removed.length > 0 && <p className="small muted">Removed: {r.removed.map((x: any) => `${x.file} (“${x.why}”, ${x.by})`).join("; ")}</p>}
      {can && <>
        <h3>Add a file</h3>
        <div className="row">
          <select value={add.file} onChange={(e) => setAdd({ ...add, file: e.target.value })}>
            <option value="">Choose a file</option>{avail.map((f) => <option key={f.ev_id} value={f.ev_id}>{f.ev_id} · {f.name}</option>)}
          </select>
          <input placeholder="Reason (required)" style={{ flex: 1 }} value={add.reason} onChange={(e) => setAdd({ ...add, reason: e.target.value })} />
          <button disabled={!add.file} onClick={() => { if (!add.reason.trim()) return setErr("A reason is required."); op({ op: "add", file: add.file, reason: add.reason }); setAdd({ file: "", reason: "" }); }}>Add</button>
        </div>
      </>}
      <p className="err">{err}</p>
      <p>{r.confirmed ? <span className="ok">List confirmed by {r.confirmed.by} on {fmt(r.confirmed.at)}.</span> : <span className="warn">Not confirmed yet.</span>}{" "}
        {can && !r.confirmed && <button className="primary" onClick={() => op({ op: "confirm" })}>Confirm list</button>}
        {!isSho && !r.confirmed && <span className="muted small"> The SHO confirms the list.</span>}</p>
    </>
  );
}
