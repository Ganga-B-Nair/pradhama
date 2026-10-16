"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { copyText, fmt, short, toast } from "@/lib/util";
import { useCase } from "./ctx";

const LABEL: Record<string, string> = { pdf: "FIR PDF", json: "JSON", manifest: "Manifest", referrals: "Referrals", bsa: "BSA s.63" };

export default function Export() {
  const { c, isSho, locked, reload } = useCase();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [opts, setOpts] = useState<string[]>(["pdf", "json", "manifest"]);
  const [fir, setFir] = useState(c.fir_no || "");
  const [err, setErr] = useState("");
  useEffect(() => { api.get(`/cases/${c.id}/exports`).then(setData); }, [c.id]);

  if (!locked) return <><h2>Export</h2><p className="muted">Exports are available after the SHO approves the case.</p></>;
  if (!data) return <><h2>Export</h2><p className="muted">Loading…</p></>;

  async function create() {
    if (!opts.length) return alert("Choose at least one export.");
    try { const x = await api.post(`/cases/${c.id}/exports`, { opts }); setData(x); reload(); toast(`Export v${x.exports[0].v} created`); } catch (e: any) { setErr(e.message); }
  }
  async function saveFir() {
    if (!fir.trim()) return;
    try { await api.post(`/cases/${c.id}/fir-number`, { text: fir }); reload(); toast("Saved"); } catch (e: any) { setErr(e.message); }
  }
  return (
    <>
      <h2>Export</h2>
      {isSho && (
        <div className="box">
          <b>Create export</b>
          {Object.entries(data.kinds).map(([k, l]) => (
            <label key={k} className="row" style={{ margin: "4px 0" }}>
              <input type="checkbox" checked={opts.includes(k)} onChange={(e) => setOpts(e.target.checked ? [...opts, k] : opts.filter((x) => x !== k))} /> {String(l)}
            </label>
          ))}
          <button className="primary" onClick={create}>Create export v{data.exports.length + 1}</button>
          <p className="muted small">Every export is written to the audit trail. Re-exporting creates a new version and keeps the old ones. The FIR page opens in a new tab: use Print / Save as PDF there.</p>
        </div>
      )}
      <p className="err">{err}</p>
      <h3>Export history</h3>
      <table>
        <thead><tr><th>Version</th><th>Created</th><th>By</th><th>Head hash</th><th>Files</th></tr></thead>
        <tbody>
          {data.exports.length ? data.exports.map((e: any) => (
            <tr key={e.v}>
              <td>v{e.v}</td><td>{fmt(e.at)}</td><td>{e.by}</td>
              <td className="mono">{short(e.head)} <button className="link small" onClick={() => copyText(e.head)}>copy</button></td>
              <td className="row">
                {e.opts.map((k: string) => <a key={k} className="linkbtn small" style={{ textDecoration: "none" }} target={["pdf", "bsa"].includes(k) ? "_blank" : undefined} rel="noreferrer" href={`/api/cases/${c.id}/exports/${e.v}/${k}`}>{LABEL[k]}</a>)}
                <button className="small" onClick={() => router.push(`/verify/${encodeURIComponent(c.ref)}/${e.head}`)}>Verify</button>
              </td>
            </tr>
          )) : <tr><td colSpan={5} className="muted">No exports yet.</td></tr>}
        </tbody>
      </table>
      <h3>Official FIR number</h3>
      <p className="muted small">Record it after filing through the official channel (outside TRACE).</p>
      <div className="row"><input value={fir} onChange={(e) => setFir(e.target.value)} placeholder="e.g. 1301/2026" disabled={!isSho} />{isSho && <button onClick={saveFir}>Save</button>}</div>
    </>
  );
}
