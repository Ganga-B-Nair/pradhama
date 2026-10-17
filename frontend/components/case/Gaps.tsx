"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmt } from "@/lib/util";
import { Chips } from "./bits";
import { useCase } from "./ctx";

export default function Gaps() {
  const { c, canEdit, setTab, reload } = useCase();
  const [gaps, setGaps] = useState<any[] | null>(null);
  const [sel, setSel] = useState<{ id: string; mode: string } | null>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [rec, setRec] = useState<{ id: string; r: MediaRecorder } | null>(null);
  const load = async () => setGaps((await api.get(`/cases/${c.id}/gaps`)).gaps);
  useEffect(() => { load(); }, [c.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!gaps) return <><h2>Gap questions</h2><p className="muted">Loading…</p></>;
  if (!gaps.length) return <><h2>Gap questions</h2><p className="muted">No questions yet. Run analysis first.</p></>;

  async function setGap(id: string, status: string, t = "", voice = false) {
    try {
      setGaps((await api.patch(`/cases/${c.id}/gaps/${id}`, { status, text: t, voice })).gaps);
      setSel(null); setText(""); reload();
    } catch (e: any) { setErr(e.message); }
  }
  async function submit() {
    if (!sel) return;
    if (!text.trim()) return setErr(sel.mode === "dismiss" ? "A reason is required to dismiss a question." : "Enter the answer.");
    setGap(sel.id, sel.mode === "dismiss" ? "dismissed" : "answered", text);
  }
  async function recheck() {
    setMsg("Re-running checks…");
    try {
      const r = await api.post(`/cases/${c.id}/gaps/recheck`);
      await load(); reload();
      setMsg(`Checks re-run in ${r.seconds} s. ${r.resolved.length ? r.resolved.length + " question(s) resolved by new records." : "No change. Upload the missing record in Evidence, then re-run."}`);
    } catch (e: any) { setMsg(e.message); }
  }
  async function voice(id: string) {
    if (rec?.id === id) return rec.r.stop();
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) return alert("Recording is not available in this browser.");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const r = new MediaRecorder(stream);
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRec(null);
        const type = r.mimeType || "audio/webm";
        const fd = new FormData();
        fd.append("files", new Blob(chunks, { type }), `gap_${id}_voice_answer.${type.includes("ogg") ? "ogg" : "webm"}`);
        try {
          const [saved] = await api.upload(`/cases/${c.id}/files`, fd);
          setGap(id, "answered", `Voice answer recorded as ${saved.ev_id || "evidence"} (sha256 ${String(saved.sha256).slice(0, 12)}…).`, true);
        } catch (e: any) { setErr(e.message); alert(e.message); }
      };
      r.start();
      setRec({ id, r });
    } catch (e: any) { alert("Microphone not available: " + e.message); }
  }

  const count = (s: string) => gaps.filter((g) => g.status === s).length;
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Gap questions</h2>{canEdit && <button onClick={recheck}>Re-run checks</button>}
      </div>
      <p className="muted">Ask these while the complainant is present. Questions describe missing information only; they are not a judgement of the complainant. Open {count("open")} · Answered {count("answered")} · Dismissed {count("dismissed")}</p>
      <p className="small">{msg}</p>
      {["High", "Medium", "Low"].map((sev) => {
        const gs = gaps.filter((g) => g.sev === sev);
        if (!gs.length) return null;
        return (
          <div key={sev}>
            <h3>{sev} ({gs.length})</h3>
            {gs.map((g) => {
              const editing = sel?.id === g.id;
              return (
                <div className="box" key={g.id}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <b>{g.q}</b>
                    {g.status === "open" ? <span className="tag warn">Open</span> : g.status === "answered" ? <span className="tag ok">Answered</span> : <span className="tag">Dismissed</span>}
                  </div>
                  {g.status !== "open" && <p className="small">{g.status === "answered" ? "Answer" : "Reason"}: {g.answer || g.reason} <span className="muted">— {g.by}, {fmt(g.at)}</span>{g.voice && <> <span className="tag">voice answer</span></>}</p>}
                  <details>
                    <summary className="small">Why this question</summary>
                    <p className="small">{g.rule}: {g.rule_text}</p>
                    {g.src.length > 0 && <p className="small">Sources: <Chips src={g.src} /></p>}
                    <p className={`small ${g.lint.length ? "bad" : "ok"}`}>Wording check: {g.lint.length ? "blocked words found: " + g.lint.join(", ") : "passed (no judgement words)"}</p>
                  </details>
                  {canEdit && g.status === "open" && !editing && (
                    <div className="row" style={{ marginTop: 6 }}>
                      <button onClick={() => { setSel({ id: g.id, mode: "answer" }); setErr(""); }}>Answer</button>
                      <button onClick={() => voice(g.id)}>{rec?.id === g.id ? "Stop voice answer" : "Answer by voice"}</button>
                      <button onClick={() => setTab("evidence")}>Add file</button>
                      <button onClick={() => setGap(g.id, "answered", "Not known to complainant")}>Not known to complainant</button>
                      <button onClick={() => { setSel({ id: g.id, mode: "dismiss" }); setErr(""); }}>Dismiss</button>
                    </div>
                  )}
                  {editing && (
                    <div style={{ marginTop: 6 }}>
                      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder={sel!.mode === "dismiss" ? "Reason for dismissing (required)" : "Answer given by the complainant"} />
                      <p className="err">{err}</p>
                      <div className="row"><button className="primary" onClick={submit}>{sel!.mode === "dismiss" ? "Dismiss" : "Save answer"}</button><button onClick={() => setSel(null)}>Cancel</button></div>
                    </div>
                  )}
                  {canEdit && g.status !== "open" && <button className="link small" onClick={() => setGap(g.id, "open")}>Reopen</button>}
                </div>
              );
            })}
          </div>
        );
      })}
    </>
  );
}
