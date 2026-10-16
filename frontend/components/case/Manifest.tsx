"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { copyText, fmt, kb, KIND_LABEL, SCREEN_TXT, short } from "@/lib/util";
import { useCase } from "./ctx";

const typeOf = (x: any) => KIND_LABEL[x.kind] || "Not analysed";

function MetaTxt({ x }: { x: any }) {
  if (!x.meta) return <span className="muted">Not analysed</span>;
  if (x.meta.status === "Conflict") return <span className="warn">Conflict</span>;
  return x.meta.status === "Available" ? <>Available</> : <span className="muted">Not available</span>;
}
export function ScreenTxt({ x }: { x: any }) {
  if (!x.screen) return <span className="muted">Not analysed</span>;
  if (x.screen.status === "review") return <><span className="warn">{SCREEN_TXT.review}</span> <span className="small">({x.screen.score})</span></>;
  return <span className={x.screen.status === "none" ? "" : "muted"}>{SCREEN_TXT[x.screen.status]}</span>;
}

export default function Manifest() {
  const { c } = useCase();
  const [data, setData] = useState<any>(null);
  const [f, setF] = useState<any>({ sort: "id", dir: 1 });
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => { api.get(`/cases/${c.id}/manifest`).then(setData); }, [c.id]);
  if (!data) return <><h2>Evidence manifest</h2><p className="muted">Loading…</p></>;

  let rows = data.files.slice();
  if (f.type) rows = rows.filter((x: any) => typeOf(x) === f.type);
  if (f.screen) rows = rows.filter((x: any) => x.screen?.status === f.screen);
  if (f.conflict) rows = rows.filter((x: any) => x.meta?.status === "Conflict");
  if (!f.expand) rows = rows.filter((x: any) => !x.dup || x.dup.canonical);
  const val = (x: any) => ({ id: x.ev_id, name: x.name, type: typeOf(x), lang: x.lang, at: x.uploaded_at, meta: x.meta?.status || "", screen: x.screen?.score ?? -1 } as any)[f.sort];
  rows.sort((a: any, b: any) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * f.dir);
  const types = Array.from(new Set(data.files.map(typeOf))) as string[];
  const th = (k: string, l: string) => (
    <th className="sort" onClick={() => setF({ ...f, sort: k, dir: f.sort === k ? -f.dir : 1 })}>{l}{f.sort === k ? (f.dir > 0 ? " ▲" : " ▼") : ""}</th>
  );
  const selected = data.files.find((x: any) => x.ev_id === sel);

  return (
    <>
      <h2>Evidence manifest</h2>
      <div className="row" style={{ marginBottom: 8 }}>
        <select value={f.type || ""} onChange={(e) => setF({ ...f, type: e.target.value })}><option value="">All types</option>{types.map((t) => <option key={t}>{t}</option>)}</select>
        <select value={f.screen || ""} onChange={(e) => setF({ ...f, screen: e.target.value })}><option value="">All screening results</option>{Object.entries(SCREEN_TXT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <label className="row"><input type="checkbox" checked={!!f.conflict} onChange={(e) => setF({ ...f, conflict: e.target.checked })} /> Metadata conflicts only</label>
        <label className="row"><input type="checkbox" checked={!!f.expand} onChange={(e) => setF({ ...f, expand: e.target.checked })} /> Show all duplicates</label>
        <span className="muted small">{rows.length} shown of {data.files.length}</span>
      </div>
      <table>
        <thead><tr>{th("id", "ID")}{th("name", "File")}{th("type", "Type")}{th("lang", "Language")}{th("at", "Uploaded")}<th>SHA-256</th><th>Duplicate group</th>{th("meta", "Metadata")}{th("screen", "Screening")}</tr></thead>
        <tbody>
          {rows.length ? rows.map((x: any) => (
            <tr key={x.id} className={`click ${sel === x.ev_id ? "sel" : ""}`} onClick={() => { setSel(x.ev_id); setTimeout(() => document.getElementById("detail")?.scrollIntoView({ block: "nearest" }), 50); }}>
              <td>{x.ev_id}</td><td>{x.name}</td><td>{typeOf(x)}</td><td>{x.lang}</td><td>{fmt(x.uploaded_at)}</td><td className="mono">{short(x.sha256)}</td>
              <td>{x.dup ? `${x.dup.group}: ${x.dup.idx} of ${x.dup.of}${x.dup.canonical ? ", canonical" : ""}` : "—"}</td>
              <td><MetaTxt x={x} /></td><td><ScreenTxt x={x} /></td>
            </tr>
          )) : <tr><td colSpan={9} className="muted">No files.</td></tr>}
        </tbody>
      </table>
      {selected ? <FileDetail f={selected} limitation={data.limitation} onClose={() => setSel(null)} /> : <p className="muted small">Select a file to see its details.</p>}
    </>
  );
}

function FileDetail({ f, limitation, onClose }: { f: any; limitation: string; onClose: () => void }) {
  const { c } = useCase();
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.get(`/cases/${c.id}/files/${f.ev_id}/view`).then(setD); }, [c.id, f.ev_id]);
  const raw = `/api/cases/${c.id}/files/${f.ev_id}/raw`;
  const preview = d?.lines ? (
    <div className="lines">{d.lines.map((t: string, i: number) => <div key={i}><span>{i + 1}</span>{t}</div>)}</div>
  ) : ["jpg", "png", "webp"].includes(f.sniff) ? <img alt={f.name} style={{ maxWidth: "100%", maxHeight: 260 }} src={raw} />
    : ["wav", "mp3", "ogg", "m4a", "webm"].includes(f.sniff) ? <audio controls src={raw} style={{ width: "100%" }} />
    : <p className="muted">No preview for this file type.</p>;
  return (
    <div className="box" id="detail">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>{f.ev_id} · {f.name}</h2>
        <div className="row"><a className="linkbtn" href={`${raw}?download=1`} style={{ textDecoration: "none" }}>Download original</a><button onClick={onClose}>Close</button></div>
      </div>
      <p className="small">SHA-256 <span className="mono">{f.sha256}</span> <button className="link small" onClick={() => copyText(f.sha256)}>copy</button> · {kb(f.size)} · uploaded {fmt(f.uploaded_at)} by {f.uploaded_by}</p>
      <div className="grid2">
        <div><h3>Preview</h3>{preview}</div>
        <div>
          <h3>Metadata <span className="small muted">· {f.meta ? f.meta.status : "not analysed"}</span></h3>
          {f.meta && Object.keys(f.meta.fields || {}).length ? (
            <table><tbody>
              {Object.entries(f.meta.fields).map(([k, v]) => <tr key={k}><th>{k}</th><td>{String(v)}</td></tr>)}
              {f.meta.geo && <tr><th>Place</th><td>{f.meta.geo}</td></tr>}
            </tbody></table>
          ) : <p className="muted">{f.meta?.why || "No metadata available. Messaging apps usually remove it; this is normal and not a concern."}</p>}
          {f.meta?.conflicts?.length > 0 && <><p className="warn">Conflicts:</p><ul>{f.meta.conflicts.map((x: string) => <li key={x}>{x}</li>)}</ul></>}
          <h3>Screening</h3>
          {!f.screen ? <p className="muted">Not analysed yet.</p> : f.screen.status === "na" ? <p className="muted">Not applicable to this file type.</p> : <>
            <p><ScreenTxt x={f} />{f.screen.score != null ? ` · confidence score ${f.screen.score}` : ""}</p>
            <ul>{(f.screen.reasons || []).map((r: string) => <li key={r}>{r}</li>)}</ul>
            <div className="note small">{limitation}</div>
          </>}
          <h3>Access log</h3>
          {d?.access_log?.length ? (
            <table className="small"><tbody>{d.access_log.map((e: any) => <tr key={e.seq}><td>{fmt(e.at)}</td><td>{e.user}</td><td>{e.action}</td></tr>)}</tbody></table>
          ) : <p className="muted">No entries.</p>}
        </div>
      </div>
    </div>
  );
}
