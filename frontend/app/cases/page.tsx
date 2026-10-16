"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import RequireUser from "@/components/RequireUser";
import { StatusTag } from "@/components/case/bits";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { cap, fmt } from "@/lib/util";

const STATUSES = ["draft", "analysing", "review", "approved", "exported"];

function Cases() {
  const { user, station } = useSession();
  const router = useRouter();
  const [cases, setCases] = useState<any[] | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  useEffect(() => { api.get("/cases").then(setCases); }, []);

  let list = (cases || []).slice();
  if (q) list = list.filter((c) => c.ref.toLowerCase().includes(q.toLowerCase()) || c.complainant.name.toLowerCase().includes(q.toLowerCase()));
  if (status) list = list.filter((c) => c.status === status);

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Cases</h2>
        <button className="primary" onClick={() => router.push("/cases/new")}>New case</button>
      </div>
      <p className="muted small">Cases registered at {station?.name} only.</p>
      <div className="row" style={{ margin: "8px 0" }}>
        <input placeholder="Search reference or name" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{cap(s)}</option>)}
        </select>
        {user?.role === "sho" && (
          <button onClick={() => setStatus("review")}>Waiting for approval ({(cases || []).filter((c) => c.status === "review").length})</button>
        )}
      </div>
      <table>
        <thead><tr><th>Reference</th><th>Complainant</th><th>Status</th><th>Created by</th><th>Last updated</th><th>Open gaps</th></tr></thead>
        <tbody>
          {cases === null ? <tr><td colSpan={6} className="muted">Loading…</td></tr> :
            list.length ? list.map((c) => (
              <tr key={c.id} className="click" onClick={() => router.push(`/cases/${c.id}`)}>
                <td>{c.ref}</td><td>{c.complainant.name}</td><td><StatusTag s={c.status} /></td><td>{c.created_by}</td>
                <td>{fmt(c.updated_at)}</td><td>{c.open_gaps || "—"}</td>
              </tr>
            )) : <tr><td colSpan={6} className="muted">No cases match.</td></tr>}
        </tbody>
      </table>
    </>
  );
}

export default function Page() {
  return <RequireUser><Cases /></RequireUser>;
}
