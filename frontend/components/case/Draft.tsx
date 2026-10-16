"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmt, KIND_LABEL } from "@/lib/util";
import { Chips } from "./bits";
import { useCase } from "./ctx";

const split = (t: string) => t.split(/(?<=[.!?])\s+(?=[A-Z0-9₹])/).map((s) => s.trim()).filter(Boolean);

export default function Draft() {
  const { c, canEdit, locked } = useCase();
  const [d, setD] = useState<any>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [refs, setRefs] = useState<number>(0);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<any>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [cmp, setCmp] = useState<[number, number] | null>(null);
  const [va, setVa] = useState(0);
  const [vb, setVb] = useState(0);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get(`/cases/${c.id}/draft`).then((x) => { setD(x); setVa(Math.max(1, x.versions.length - 1)); setVb(x.versions.length); });
    api.get(`/cases/${c.id}/manifest`).then((m) => setFiles(m.files));
    api.get(`/cases/${c.id}/referrals`).then((r) => setRefs(r.items.length));
  }, [c.id]);
  if (!d) return <><h2>Draft FIR</h2><p className="muted">Loading…</p></>;

  const versions = d.versions;
  async function save() {
    try {
      const x = await api.put(`/cases/${c.id}/draft`, { fields: form.fields, narrative: form.narrative, note: versions.length ? "Officer edit" : "Written by hand" });
      setD(x); setEditing(false); setVb(x.versions.length); setVa(Math.max(1, x.versions.length - 1));
    } catch (e: any) { setErr(e.message); }
  }

  if (!versions.length) {
    return <>
      <h2>Draft FIR</h2><p className="muted">No draft yet. Run analysis to generate one.</p>
      {canEdit && !editing && <button onClick={() => { setForm({ fields: { place: c.complainant.address, period: "", report_date: fmt(c.created_at, false), delay_reason: "" }, narrative: "" }); setEditing(true); }}>Write the draft by hand</button>}
      {editing && <Editor form={form} setForm={setForm} save={save} cancel={() => setEditing(false)} next={1} err={err} />}
    </>;
  }
  const v = versions[versions.length - 1], F = v.fields, P = c.complainant;
  const sents: any[] = v.sentences?.length ? v.sentences : split(v.narrative).map((t) => ({ t, src: [], supported: null }));
  const byKind = files.reduce((a: any, f: any) => { const k = KIND_LABEL[f.kind] || "Not analysed"; a[k] = (a[k] || 0) + 1; return a; }, {});
  const evSum = `${files.length} files: ` + Object.entries(byKind).map(([k, n]) => `${n} ${k.toLowerCase()}`).join(", ") + `. ${refs} referred for forensic review.`;
  const unsupported = sents.filter((s) => s.supported === false).length;
  const hs = hover !== null ? sents[hover] : null;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Draft FIR · v{v.v}</h2>
        <span className={`tag ${v.edited ? "ok" : "warn"}`}>{v.edited ? `Edited by officer (v${v.v})` : "Machine-generated draft: review before use"}</span>
      </div>
      {editing ? <Editor form={form} setForm={setForm} save={save} cancel={() => setEditing(false)} next={versions.length + 1} err={err} /> : <>
        <table style={{ maxWidth: 900 }}><tbody>
          <tr><th>Complainant</th><td>{P.name}, {P.address} · {P.contact}</td></tr>
          <tr><th>Place of occurrence</th><td>{F.place}</td></tr>
          <tr><th>Date and time of occurrence</th><td>{F.period}</td></tr>
          <tr><th>Date of report</th><td>{F.report_date}</td></tr>
          <tr><th>Reason for delay</th><td>{F.delay_reason || <span className="muted">Not recorded</span>}</td></tr>
          <tr><th>Evidence summary</th><td>{evSum}</td></tr>
        </tbody></table>
        <h3>Narrative</h3>
        {unsupported > 0 && <div className="note badbar small">{unsupported} sentence(s) marked <b>Unsupported — needs officer review</b>: they cite no valid event, or state an amount none of their events carry.</div>}
        <div className="box" style={{ maxWidth: 900 }}>
          {sents.map((s, i) => (
            <span key={i}><span className={`sent ${hover === i ? "on" : ""} ${s.supported === false ? "unsup" : ""}`} onMouseEnter={() => setHover(i)}>{s.t}</span>{s.supported === false && <span className="bad small"> [Unsupported — needs officer review]</span>} </span>
          ))}
        </div>
        <div className="small muted">
          {!hs ? "Point at a sentence to see its sources." : hs.src?.length ? <>Sources for the highlighted sentence: <Chips src={hs.src} /></> :
            hs.supported === false ? "This sentence has no valid source. Check it against the evidence or remove it." :
              "This sentence was written or changed by the officer, so it has no machine source link."}
        </div>
        {v.model && <p className="muted small">Written by {v.model}.</p>}
        {canEdit && <p><button className="primary" onClick={() => { setForm({ fields: { ...F }, narrative: v.narrative }); setEditing(true); setErr(""); }}>Edit draft</button></p>}
        <p className="muted small">TRACE never submits or files the FIR. After approval and export, the officer files it through the official channel.</p>
      </>}
      <h3>Versions</h3>
      <table style={{ maxWidth: 900 }}>
        <thead><tr><th>Version</th><th>By</th><th>Saved</th><th>Note</th></tr></thead>
        <tbody>{versions.slice().reverse().map((x: any) => (
          <tr key={x.v}><td>v{x.v}{c.approval.version === x.v && locked && <> <span className="tag ok">approved</span></>}</td><td>{x.by}</td><td>{fmt(x.at)}</td><td>{x.note}</td></tr>
        ))}</tbody>
      </table>
      {versions.length > 1 && (
        <div className="row" style={{ marginTop: 8 }}>
          Compare <select value={va} onChange={(e) => setVa(+e.target.value)}>{versions.map((x: any) => <option key={x.v} value={x.v}>v{x.v}</option>)}</select> with
          <select value={vb} onChange={(e) => setVb(+e.target.value)}>{versions.map((x: any) => <option key={x.v} value={x.v}>v{x.v}</option>)}</select>
          <button onClick={() => setCmp([va, vb])}>Compare</button>
        </div>
      )}
      {cmp && <Diff a={versions.find((x: any) => x.v === cmp[0])} b={versions.find((x: any) => x.v === cmp[1])} />}
      <details style={{ marginTop: 12 }}>
        <summary>Malayalam for reading back to the complainant</summary>
        <p className="ml box">{d.ml_readback || "No Malayalam transcript for this case (typed or English narration)."}</p>
        <p className="small muted">{d.ml_readback ? "The complainant's own words from the Malayalam transcript of the narration. TRACE does not machine-write Malayalam; read the English draft against this before filing." : ""}</p>
      </details>
    </>
  );
}

function Editor({ form, setForm, save, cancel, next, err }: any) {
  const set = (k: string) => (e: any) => setForm({ ...form, fields: { ...form.fields, [k]: e.target.value } });
  return <>
    <div className="form">
      <label>Place of occurrence</label><input value={form.fields.place} onChange={set("place")} />
      <label>Date and time of occurrence</label><input value={form.fields.period} onChange={set("period")} />
      <label>Date of report</label><input value={form.fields.report_date} onChange={set("report_date")} />
      <label>Reason for delay in reporting</label><input value={form.fields.delay_reason} onChange={set("delay_reason")} />
    </div>
    <h3>Narrative</h3>
    <textarea rows={12} value={form.narrative} onChange={(e) => setForm({ ...form, narrative: e.target.value })} />
    <p className="err">{err}</p>
    <div className="row" style={{ marginTop: 8 }}><button className="primary" onClick={save}>Save as v{next}</button><button onClick={cancel}>Cancel</button></div>
  </>;
}

function Diff({ a, b }: { a: any; b: any }) {
  if (!a || !b) return null;
  const x = split(a.narrative), y = split(b.narrative), n = x.length, m = y.length;
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = x[i] === y[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: JSX.Element[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { out.push(<span key={out.length}>{x[i]} </span>); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) out.push(<del key={out.length} className="bad">{x[i++]} </del>);
    else out.push(<ins key={out.length} className="ok">{y[j++]} </ins>);
  }
  while (i < n) out.push(<del key={out.length} className="bad">{x[i++]} </del>);
  while (j < m) out.push(<ins key={out.length} className="ok">{y[j++]} </ins>);
  const fd = Object.keys(b.fields).filter((k) => a.fields[k] !== b.fields[k]);
  return (
    <div className="box"><b>v{a.v} → v{b.v}</b>
      {fd.length > 0 && <ul className="small">{fd.map((k) => <li key={k}>{k}: “{a.fields[k]}” → “{b.fields[k]}”</li>)}</ul>}
      <p>{out}</p>
    </div>
  );
}
