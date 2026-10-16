"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { tc } from "@/lib/util";
import { Modal } from "./bits";
import { Src, useCase } from "./ctx";

/** Opens the original behind a source chip, with the cited line highlighted.
 *  Viewing an original is written to the audit trail by the API. */
export default function SourceModal({ src, onClose }: { src: Src; onClose: () => void }) {
  const { c, segments } = useCase();
  const [f, setF] = useState<any>(null);
  const [err, setErr] = useState("");
  const hl = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (src.f) api.get(`/cases/${c.id}/files/${src.f}/view?line=${src.l || 0}`).then(setF).catch((e) => setErr(e.message));
  }, [src, c.id]);
  useEffect(() => { hl.current?.scrollIntoView({ block: "center" }); }, [f]);

  if (src.n) {
    const s = segments.find((x) => x.id === src.n);
    return (
      <Modal onClose={onClose}>
        {!s ? <p>Narration segment not found.</p> : <>
          <h2>Narration segment {s.id}{s.end ? ` · ${tc(s.t)}–${tc(s.end)}` : ""}</h2>
          <div className="grid2">
            <div><b>Malayalam (original)</b><p className="ml">{s.ml || "—"}</p></div>
            <div><b>English</b><p>{s.en}</p>
              <p className={`small ${s.edited ? "warn" : "muted"}`}>{s.edited ? "Edited by officer" : "Machine translation"}</p></div>
          </div>
          {s.end > 0 && <NarrationClip s={s} />}
        </>}
      </Modal>
    );
  }
  return (
    <Modal onClose={onClose}>
      {err ? <p>{err}</p> : !f ? <p className="muted">Loading…</p> : <>
        <h2>{f.ev_id} · {f.name}</h2>
        <p className="muted small">SHA-256 <span className="mono">{f.sha256}</span> · viewing is recorded in the audit trail</p>
        {f.lines ? (
          <div className="lines">
            {f.lines.map((t: string, i: number) => (
              <div key={i} className={i + 1 === src.l ? "hl" : ""} ref={i + 1 === src.l ? hl : undefined}><span>{i + 1}</span>{t}</div>
            ))}
          </div>
        ) : ["jpg", "png", "webp"].includes(f.sniff) ? (
          <img alt={f.name} style={{ maxWidth: "100%", maxHeight: 360 }} src={`/api/cases/${c.id}/files/${f.ev_id}/raw`} />
        ) : ["wav", "mp3", "ogg", "m4a", "webm"].includes(f.sniff) ? (
          <audio controls src={`/api/cases/${c.id}/files/${f.ev_id}/raw`} style={{ width: "100%" }} />
        ) : <p className="muted">No preview for this file type.</p>}
        {f.meta && Object.keys(f.meta.fields || {}).length > 0 && <>
          <h3>Metadata</h3>
          <table><tbody>
            {Object.entries(f.meta.fields).map(([k, v]) => <tr key={k}><th>{k}</th><td>{String(v)}</td></tr>)}
            {f.meta.geo && <tr><th>Place</th><td>{f.meta.geo}</td></tr>}
          </tbody></table>
        </>}
      </>}
    </Modal>
  );
}

function NarrationClip({ s }: { s: any }) {
  const { c } = useCase();
  const ref = useRef<HTMLAudioElement>(null);
  const [ev, setEv] = useState<string | null>(null);
  useEffect(() => { api.get(`/cases/${c.id}/narration`).then((n) => setEv(n?.audio_ev || null)); }, [c.id]);
  if (!ev) return null;
  const play = () => {
    const a = ref.current;
    if (!a) return;
    a.currentTime = s.t;
    a.play();
    const stop = () => { if (a.currentTime >= s.end) { a.pause(); a.removeEventListener("timeupdate", stop); } };
    a.addEventListener("timeupdate", stop);
  };
  return <div className="row"><audio ref={ref} src={`/api/cases/${c.id}/files/${ev}/raw`} preload="metadata" /><button onClick={play}>Play segment</button></div>;
}
