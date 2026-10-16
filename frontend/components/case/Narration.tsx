"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmt, tc } from "@/lib/util";
import { useCase } from "./ctx";

export default function Narration() {
  const { c, canEdit, setTab, reload, reloadNarration } = useCase();
  const [n, setN] = useState<any>(undefined);
  const [manual, setManual] = useState(false);
  const [typed, setTyped] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [edit, setEdit] = useState({ ml: "", en: "" });
  const [showMachine, setShowMachine] = useState<number | null>(null);
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [recSecs, setRecSecs] = useState(0);
  const [err, setErr] = useState("");
  const audio = useRef<HTMLAudioElement>(null);

  const load = async () => { setN(await api.get(`/cases/${c.id}/narration`)); };
  useEffect(() => { load(); }, [c.id]); // eslint-disable-line react-hooks/exhaustive-deps
  // Poll while speech-to-text runs in the background worker.
  useEffect(() => {
    if (!n || !["pending", "transcribing"].includes(n.status)) return;
    const t = setInterval(async () => {
      const x = await api.get(`/cases/${c.id}/narration`);
      setN(x);
      if (x?.status === "done") { reloadNarration(); reload(); }
    }, 2000);
    return () => clearInterval(t);
  }, [n?.status, c.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!c.complainant.consent_at) return <><h2>Narration</h2><div className="note warnbar">Record consent first.</div></>;
  if (n === undefined) return <><h2>Narration</h2><p className="muted">Loading…</p></>;

  async function sendAudio(blob: Blob, name: string, source: string) {
    setErr("");
    const fd = new FormData();
    fd.append("file", blob, name);
    fd.append("source", source);
    try { setN(await api.upload(`/cases/${c.id}/narration`, fd)); reload(); } catch (e: any) { setErr(e.message); }
  }
  async function startRec() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) return alert("Recording is not available in this browser. Use Upload audio or type the narration.");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const r = new MediaRecorder(stream);
      const start = Date.now();
      const timer = setInterval(() => setRecSecs(Math.round((Date.now() - start) / 1000)), 500);
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        clearInterval(timer);
        setRec(null);
        const type = r.mimeType || "audio/webm";
        sendAudio(new Blob(chunks, { type }), `counter_recording.${type.includes("ogg") ? "ogg" : "webm"}`, `Recorded at counter (${tc(Math.round((Date.now() - start) / 1000))})`);
      };
      r.start();
      setRecSecs(0);
      setRec(r);
    } catch (e: any) { alert("Microphone not available: " + e.message + ". Use Upload audio or type the narration."); }
  }
  async function saveTyped() {
    if (!typed.trim()) return;
    try { setN(await api.post(`/cases/${c.id}/narration/typed`, { text: typed })); setManual(false); reloadNarration(); reload(); } catch (e: any) { setErr(e.message); }
  }
  async function replace() {
    if (!confirm("Replace the narration? The current version stays in the audit trail and the audio stays in evidence.")) return;
    await api.del(`/cases/${c.id}/narration`);
    setN(null); reloadNarration(); reload();
  }
  async function saveSeg(id: number) {
    try {
      setN(await api.patch(`/cases/${c.id}/narration/segments/${id}`, n.manual ? { en: edit.en } : edit));
      setSel(null); reloadNarration(); reload();
    } catch (e: any) { setErr(e.message); }
  }
  function playSeg(s: any) {
    const a = audio.current;
    if (!a) return;
    a.currentTime = s.t;
    a.play();
    const stop = () => { if (a.currentTime >= s.end) { a.pause(); a.removeEventListener("timeupdate", stop); } };
    a.addEventListener("timeupdate", stop);
  }

  if (!n) {
    if (!canEdit) return <><h2>Narration</h2><p className="muted">No narration recorded.</p></>;
    return (
      <>
        <h2>Narration</h2>
        <p className="muted">Record the complainant&apos;s account at the counter, upload an audio file, or type it if transcription isn&apos;t possible.</p>
        <div className="box">
          <div className="row">
            {rec ? <><button className="danger" onClick={() => rec.stop()}>Stop recording</button> <span className="mono">{tc(recSecs)}</span></>
              : <button className="primary" onClick={startRec}>Record</button>}
            <span className="muted">or</span>
            <label className="linkbtn">Upload audio<input type="file" accept=".ogg,.opus,.mp3,.m4a,.wav,.webm,audio/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) sendAudio(f, f.name, `Uploaded audio: ${f.name}`); e.target.value = ""; }} /></label>
            <span className="muted">or</span>
            <button onClick={() => setManual(true)}>Type narration instead</button>
          </div>
          <p className="muted small">Speech-to-text runs on this station&apos;s server (faster-whisper, Malayalam): one pass keeps the Malayalam original, a second pass translates to English.</p>
          {manual && <>
            <h3>Typed narration</h3>
            <textarea rows={6} value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type the complainant's account in English" />
            <p><button className="primary" onClick={saveTyped}>Save narration</button></p>
          </>}
          <p className="err">{err}</p>
        </div>
      </>
    );
  }

  const busy = ["pending", "transcribing"].includes(n.status);
  return (
    <>
      <h2>Narration</h2>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <p>{n.source} · Detected language: <b>{n.lang}</b>{" "}
          {!n.manual && <><span className="tag">Machine transcription</span> <span className="tag">Machine translation</span>{n.model && <span className="muted small"> · {n.model}</span>}</>}</p>
        {canEdit && !busy && <button className="small" onClick={replace}>Replace narration</button>}
      </div>
      {n.audio_ev && <audio ref={audio} controls src={`/api/cases/${c.id}/files/${n.audio_ev}/raw`} style={{ width: "100%", maxWidth: 520 }} />}
      {busy && <div className="note">{n.status === "pending" ? "Waiting for the speech-to-text worker…" : "Transcribing and translating… (this runs on the station server and can take a few minutes on CPU)"}</div>}
      {n.status === "failed" && <div className="note badbar">Transcription did not complete: {n.error}. {canEdit && <><button className="link" onClick={async () => setN(await api.post(`/cases/${c.id}/narration/retry`))}>Retry</button>, or replace it with a typed narration.</>}</div>}
      {n.segments.length > 0 && <>
        <table>
          <thead><tr><th>#</th><th>Time</th><th>{n.manual ? "—" : "Malayalam (original)"}</th><th>English</th><th></th></tr></thead>
          <tbody>
            {n.segments.map((s: any) => sel === s.id ? (
              <tr key={s.id} className="sel">
                <td>{s.id}</td><td className="mono">{tc(s.t)}</td>
                <td>{n.manual ? "—" : <textarea rows={3} className="ml" value={edit.ml} onChange={(e) => setEdit({ ...edit, ml: e.target.value })} />}</td>
                <td><textarea rows={3} value={edit.en} onChange={(e) => setEdit({ ...edit, en: e.target.value })} /></td>
                <td><button className="primary small" onClick={() => saveSeg(s.id)}>Save</button> <button className="small" onClick={() => setSel(null)}>Cancel</button></td>
              </tr>
            ) : (
              <tr key={s.id}>
                <td>{s.id}</td><td className="mono">{tc(s.t)}</td><td className="ml">{s.ml || "—"}</td>
                <td>{s.en}
                  {s.edited && <div className="small warn">Edited by officer ({s.edited_by}, {fmt(s.edited_at)}) · <button className="link small" onClick={() => setShowMachine(showMachine === s.id ? null : s.id)}>{showMachine === s.id ? "hide" : "show"} machine version</button></div>}
                  {showMachine === s.id && <div className="small muted">Machine: {s.ml_machine} / {s.en_machine}</div>}
                </td>
                <td className="row">
                  {n.audio_ev && s.end > 0 && <button className="small" onClick={() => playSeg(s)}>Play</button>}
                  {canEdit && <button className="small" onClick={() => { setSel(s.id); setEdit({ ml: s.ml, en: s.en }); }}>Correct</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">Names, numbers and amounts are kept as spoken in the original. Corrections keep the machine version and are written to the audit trail.</p>
      </>}
      <p className="err">{err}</p>
      {canEdit && !busy && <p><button className="primary" onClick={() => setTab("analysis")}>Continue to Analysis</button></p>}
    </>
  );
}
