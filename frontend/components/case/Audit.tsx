"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { csv, download, fmt, short } from "@/lib/util";
import { useCase } from "./ctx";

export default function Audit() {
  const { c } = useCase();
  const [chain, setChain] = useState<any[] | null>(null);
  const [res, setRes] = useState<any>(null);
  const [f, setF] = useState<any>({});
  useEffect(() => { api.get(`/cases/${c.id}/audit`).then(setChain); }, [c.id]);
  if (!chain) return <><h2>Audit trail · {c.ref}</h2><p className="muted">Loading…</p></>;

  let rows = chain.slice();
  if (f.action) rows = rows.filter((e) => e.action === f.action);
  if (f.user) rows = rows.filter((e) => e.user === f.user);
  const bad = res?.bad?.seq;
  const verify = async () => { setChain(await api.get(`/cases/${c.id}/audit`)); setRes(await api.post(`/cases/${c.id}/audit/verify`)); };
  const exportCsv = () => download(`audit_${c.ref}.csv`, csv([["seq", "time", "user", "action", "detail", "prev_hash", "entry_hash"], ...chain.map((e) => [e.seq, e.at, e.user, e.action, e.detail, e.prev, e.hash])]), "text/csv");

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Audit trail · {c.ref}</h2>
        <div className="row"><button className="primary" onClick={verify}>Verify chain</button><button onClick={exportCsv}>Export CSV</button></div>
      </div>
      <p className="muted small">Each entry&apos;s hash = SHA-256(previous hash + entry). Read-only. Raw files, transcripts, timeline, gap questions and every draft version are recorded here with their own hashes.</p>
      {res && <div className={`note ${res.ok ? "okbar" : "badbar"}`}>{res.ok ? `Chain intact: ${res.count} entries verified.` : `Chain broken at entry #${bad} (${fmt(res.bad.at)}, ${res.bad.action}).`}</div>}
      <div className="row" style={{ marginBottom: 8 }}>
        <select value={f.action || ""} onChange={(e) => setF({ ...f, action: e.target.value })}><option value="">All actions</option>{Array.from(new Set(chain.map((e) => e.action))).sort().map((a) => <option key={a}>{a}</option>)}</select>
        <select value={f.user || ""} onChange={(e) => setF({ ...f, user: e.target.value })}><option value="">All users</option>{Array.from(new Set(chain.map((e) => e.user))).map((u) => <option key={u}>{u}</option>)}</select>
      </div>
      <table>
        <thead><tr><th>#</th><th>Time</th><th>User</th><th>Action</th><th>Detail</th><th>Entry hash</th></tr></thead>
        <tbody>{rows.slice().reverse().map((e) => (
          <tr key={e.seq} className={e.seq === bad ? "hl" : ""}>
            <td>{e.seq}</td><td>{fmt(e.at)}</td><td>{e.user}</td><td>{e.action}</td>
            <td className="small" style={{ wordBreak: "break-all" }}>{e.detail}</td><td className="mono">{short(e.hash)}</td>
          </tr>
        ))}</tbody>
      </table>
    </>
  );
}
