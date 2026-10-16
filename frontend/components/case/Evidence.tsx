"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { copyText, kb, short } from "@/lib/util";
import { useCase } from "./ctx";

type Row = { id: string; name: string; size: number; status: string; reason?: string; sha256?: string; ev_id?: string };

export default function Evidence() {
  const { c, canEdit, locked, setTab, reload } = useCase();
  const [rows, setRows] = useState<Row[]>([]);
  const [pending, setPending] = useState<Row[]>([]);
  const [over, setOver] = useState(false);
  const load = () => api.get(`/cases/${c.id}/files`).then(setRows);
  useEffect(() => { load(); }, [c.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!c.complainant.consent_at)
    return <><h2>Evidence upload</h2><div className="note warnbar">Record the complainant&apos;s consent first. <button className="link" onClick={() => setTab("complainant")}>Go to Complainant</button></div></>;

  async function addFiles(list: FileList | null) {
    if (!list) return;
    for (const file of Array.from(list)) {
      const tmp: Row = { id: "tmp" + Math.random(), name: file.name, size: file.size, status: "Hashing and checking" };
      setPending((p) => [...p, tmp]);
      const fd = new FormData();
      fd.append("files", file);
      try { await api.upload(`/cases/${c.id}/files`, fd); }
      catch (e: any) { alert(e.message); }
      setPending((p) => p.filter((x) => x.id !== tmp.id));
      await load();
    }
    await reload();
  }
  async function clearRow(id: string) { await api.del(`/cases/${c.id}/files/${id}`); load(); }

  const total = rows.filter((r) => r.status === "accepted").reduce((a, r) => a + r.size, 0);
  const all = [...pending, ...rows.slice().reverse()];
  return (
    <>
      <h2>Evidence upload</h2>
      <p className="muted">Allowed: JPG, PNG, WEBP, HEIC, PDF, TXT, CSV, XLSX, ZIP (chat export), OGG/OPUS, MP3, M4A, WAV. Limits: 50 MB per file, 500 MB per case ({kb(total)} used). Each file is hashed with SHA-256 on arrival, before anything else reads it.</p>
      {canEdit ? (
        <div className={`drop ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); addFiles(e.dataTransfer.files); }}>
          Drag files here or <label className="linkbtn">choose files<input type="file" multiple hidden onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} /></label>
        </div>
      ) : <div className="note">{locked ? "The case is approved; files can no longer be added." : "Uploads are paused while analysis runs."}</div>}
      <table>
        <thead><tr><th>File</th><th>Size</th><th>Status</th><th>SHA-256</th><th>Evidence ID</th><th></th></tr></thead>
        <tbody>
          {all.length ? all.map((r) => (
            <tr key={r.id}>
              <td>{r.name}{r.ev_id && rows.find((x) => x.id === r.id && (x as any).narration) ? <span className="muted small"> (narration)</span> : null}</td>
              <td>{kb(r.size)}</td>
              <td>{r.status === "accepted" ? <span className="ok">Accepted</span> : r.status === "rejected" ? <><span className="bad">Rejected</span> <span className="small">{r.reason}</span></> : <span className="warn">{r.status}…</span>}</td>
              <td>{r.sha256 ? <><span className="mono">{short(r.sha256)}</span> <button className="link small" onClick={() => copyText(r.sha256!)}>copy</button></> : "—"}</td>
              <td>{r.ev_id || "—"}</td>
              <td>{r.status === "rejected" && canEdit && <button className="small" onClick={() => clearRow(r.id)}>Remove</button>}</td>
            </tr>
          )) : <tr><td colSpan={6} className="muted">No files yet.</td></tr>}
        </tbody>
      </table>
      <p className="muted small">Accepted files can&apos;t be removed; they are part of the custody record. Rejected rows can be cleared from this list.</p>
      <p><button className="primary" onClick={() => setTab("narration")}>Continue to Narration</button></p>
    </>
  );
}
