"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { copyText, kb, short } from "@/lib/util";
import { useCase } from "./ctx";

type Row = { id: string; name: string; size: number; status: string; reason?: string; sha256?: string; ev_id?: string; narration?: boolean };
type Limit = { max: number; used: number; left: number; max_file_mb: number; allowed: string[] };

const ext = (name: string) => (name.includes(".") ? "." + name.split(".").pop()!.toLowerCase() : "");

export default function Evidence() {
  const { c, canEdit, locked, setTab, reload } = useCase();
  const [rows, setRows] = useState<Row[]>([]);
  const [limit, setLimit] = useState<Limit | null>(null);
  const [staged, setStaged] = useState<File[]>([]);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = async () => {
    setRows(await api.get(`/cases/${c.id}/files`));
    setLimit(await api.get(`/cases/${c.id}/files/limit`));
  };
  useEffect(() => { load(); }, [c.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!c.complainant.consent_at)
    return <><h2>Evidence upload</h2><div className="note warnbar">Record the complainant&apos;s consent first. <button className="link" onClick={() => setTab("complainant")}>Go to Complainant</button></div></>;
  if (!limit) return <><h2>Evidence upload</h2><p className="muted">Loading…</p></>;

  const problem = (f: File) =>
    !limit.allowed.includes(ext(f.name)) ? `File type ${ext(f.name) || "(none)"} is not allowed`
      : f.size > limit.max_file_mb * 1048576 ? `Larger than ${limit.max_file_mb} MB` : "";

  function addToSelection(list: FileList | null) {
    if (!list) return;
    const incoming = Array.from(list).filter((f) => !staged.some((s) => s.name === f.name && s.size === f.size));
    const room = limit!.left - staged.length;
    if (incoming.length > room) setMsg(`Only ${Math.max(room, 0)} more file(s) can be added: a case holds up to ${limit!.max} evidence files.`);
    else setMsg("");
    setStaged([...staged, ...incoming.slice(0, Math.max(room, 0))]);
  }

  async function upload() {
    const ok = staged.filter((f) => !problem(f));
    if (!ok.length) return;
    setBusy(true);
    setMsg("");
    const fd = new FormData();
    ok.forEach((f) => fd.append("files", f));
    try {
      const res: Row[] = await api.upload(`/cases/${c.id}/files`, fd);
      const rejected = res.filter((r) => r.status === "rejected").length;
      setMsg(`${res.length - rejected} file(s) accepted and hashed${rejected ? `, ${rejected} rejected (see below)` : ""}.`);
      setStaged([]);
    } catch (e: any) { setMsg(e.message); }
    setBusy(false);
    await load();
    await reload();
  }
  async function clearRow(id: string) { await api.del(`/cases/${c.id}/files/${id}`); load(); }

  const evidence = rows.filter((r) => !r.narration);
  const full = limit.left <= 0;
  const bad = staged.filter(problem).length;
  return (
    <>
      <h2>Evidence upload</h2>
      <p className="muted">Up to {limit.max} files per case. Allowed: JPG, PNG, WEBP, HEIC, PDF, TXT, CSV, XLSX, ZIP (chat export), OGG/OPUS, MP3, M4A, WAV; {limit.max_file_mb} MB per file. Each file is hashed with SHA-256 on arrival, before anything else reads it, and the original is stored in the station&apos;s database.</p>
      <p><b>{limit.used} of {limit.max}</b> evidence files used{limit.left > 0 ? ` · ${limit.left} remaining` : " · limit reached"}.</p>

      {!canEdit ? <div className="note">{locked ? "The case is approved; files can no longer be added." : "Uploads are paused while analysis runs."}</div>
        : full ? <div className="note warnbar">This case already has {limit.max} evidence files, the maximum.</div> : (
          <div className="box">
            <h3 style={{ marginTop: 0 }}>Add evidence files</h3>
            <div className={`drop ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); addToSelection(e.dataTransfer.files); }}>
              Drag files here or <label className="linkbtn">choose files<input type="file" multiple hidden onChange={(e) => { addToSelection(e.target.files); e.target.value = ""; }} /></label>
              <div className="muted small" style={{ marginTop: 6 }}>{staged.length} selected · room for {limit.left - staged.length} more</div>
            </div>
            {staged.length > 0 && <>
              <table>
                <thead><tr><th>#</th><th>File</th><th>Size</th><th>Check</th><th></th></tr></thead>
                <tbody>{staged.map((f, i) => (
                  <tr key={f.name + f.size}>
                    <td>{i + 1}</td><td>{f.name}</td><td>{kb(f.size)}</td>
                    <td>{problem(f) ? <span className="bad">{problem(f)}</span> : <span className="ok">Ready</span>}</td>
                    <td><button className="small" onClick={() => setStaged(staged.filter((_, j) => j !== i))}>Remove</button></td>
                  </tr>
                ))}</tbody>
              </table>
              <div className="row" style={{ marginTop: 8 }}>
                <button className="primary" disabled={busy || staged.length === bad} onClick={upload}>{busy ? "Uploading and hashing…" : `Upload ${staged.length - bad} file(s)`}</button>
                <button disabled={busy} onClick={() => { setStaged([]); setMsg(""); }}>Clear selection</button>
                {bad > 0 && <span className="muted small">{bad} file(s) can&apos;t be uploaded and will be skipped.</span>}
              </div>
            </>}
          </div>
        )}
      <p className="small">{msg}</p>

      <h3>Uploaded evidence</h3>
      <table>
        <thead><tr><th>File</th><th>Size</th><th>Status</th><th>SHA-256</th><th>Evidence ID</th><th></th></tr></thead>
        <tbody>
          {evidence.length ? evidence.slice().reverse().map((r) => (
            <tr key={r.id}>
              <td>{r.name}</td><td>{kb(r.size)}</td>
              <td>{r.status === "accepted" ? <span className="ok">Accepted</span> : <><span className="bad">Rejected</span> <span className="small">{r.reason}</span></>}</td>
              <td>{r.sha256 ? <><span className="mono">{short(r.sha256)}</span> <button className="link small" onClick={() => copyText(r.sha256!)}>copy</button></> : "—"}</td>
              <td>{r.ev_id || "—"}</td>
              <td>{r.status === "rejected" && canEdit && <button className="small" onClick={() => clearRow(r.id)}>Remove</button>}</td>
            </tr>
          )) : <tr><td colSpan={6} className="muted">No files yet.</td></tr>}
        </tbody>
      </table>
      <p className="muted small">Accepted files can&apos;t be removed; they are part of the custody record. Rejected rows don&apos;t count toward the limit and can be cleared from this list. The narration recording is added under Narration and doesn&apos;t use an evidence slot.</p>
      <p><button className="primary" onClick={() => setTab("narration")}>Continue to Narration</button></p>
    </>
  );
}
