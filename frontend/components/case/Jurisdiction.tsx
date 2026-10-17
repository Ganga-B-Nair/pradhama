"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmt, short } from "@/lib/util";
import { Chip } from "./bits";
import { useCase } from "./ctx";

type Station = { name: string; link: string | null; distance_km: number | null; source: string; recommended: boolean };
type Recipient = { name: string; link: string | null; pin: string | null; source: string; recommended: boolean };

const VERDICT: Record<string, { cls: string; icon: string; txt: string }> = {
  match: { cls: "ok", icon: "✓", txt: "Sources agree" },
  partial: { cls: "warn", icon: "!", txt: "Partly agree" },
  mismatch: { cls: "bad", icon: "✗", txt: "Sources disagree" },
  unverified: { cls: "", icon: "?", txt: "Not cross-checked" },
};
const STATUS_CLS: Record<string, string> = {
  "Awaiting SHO approval": "warn", "Approved for dispatch": "ok", "Returned by SHO": "bad", Dispatched: "ok",
};
const key = (r: { pin: string | null; name: string }) => `${r.pin || ""}|${r.name}`;

function Verdict({ v }: { v: string }) {
  const x = VERDICT[v] || VERDICT.unverified;
  return <span className={`tag ${x.cls}`}>{x.icon} {x.txt}</span>;
}

export default function Jurisdiction() {
  const { c, isSho } = useCase();
  const [st, setSt] = useState<any>(null);
  const [notices, setNotices] = useState<any[]>([]);
  const [pins, setPins] = useState<string[]>([]);
  const [newPin, setNewPin] = useState("");
  const [refresh, setRefresh] = useState(false);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [rcpt, setRcpt] = useState<Record<string, Recipient>>({});
  const [manual, setManual] = useState({ name: "", link: "", pin: "" });
  const [draft, setDraft] = useState({ kind: "", subject: "", body: "" });
  const [confirmed, setConfirmed] = useState(false);
  const [dispatch, setDispatch] = useState<Record<string, { channel: string; note: string }>>({});

  const load = async () => {
    const s = await api.get(`/cases/${c.id}/jurisdiction`);
    setSt(s);
    setPins((p) => (p.length ? p : s.pins.filter((x: any) => !x.lookup).map((x: any) => x.pin)));
  };
  useEffect(() => {
    load().catch((e) => setErr(e.message));
    api.get(`/cases/${c.id}/notices`).then(setNotices).catch(() => {});
  }, [c.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!st) return <><h2>Jurisdiction Lookup</h2><p className="muted">{err || "Loading…"}</p></>;

  async function run(fn: () => Promise<any>, label: string) {
    setErr(""); setBusy(label);
    try { await fn(); } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  }
  const addPin = () => run(async () => {
    const s = await api.post(`/cases/${c.id}/jurisdiction/pins`, { pin: newPin });
    setSt(s); setPins((p) => Array.from(new Set([...p, newPin.trim()]))); setNewPin("");
  }, "pin");
  const lookup = () => run(async () => {
    setSt(await api.post(`/cases/${c.id}/jurisdiction/lookup`, { pins, refresh }));
  }, "lookup");
  const toggle = (r: Recipient) => setRcpt((m) => {
    const n = { ...m };
    if (n[key(r)]) delete n[key(r)]; else n[key(r)] = r;
    setConfirmed(false);
    return n;
  });
  const recipients = Object.values(rcpt);
  const offRec = recipients.filter((r) => !r.recommended);

  function fill(kind: string) {
    const used = new Set(recipients.map((r) => r.pin).filter(Boolean));
    const lines = st.pins.filter((p: any) => used.has(p.pin)).flatMap((p: any) => p.traces.map((t: any) =>
      `- PIN ${p.pin}${t.area ? ` (${t.area})` : ""}: IP ${t.ip}${t.at ? ` on ${fmt(t.at)}` : ""}${t.isp ? ` via ${t.isp}` : ""} [${t.src.f} line ${t.src.l}]`));
    const facts = lines.length ? lines.join("\n") : "- [Add the addresses, times and area here]";
    const ask: Record<string, string> = {
      "Suspect information": "We share this so your station is aware of activity linked to a suspect in this case. Details of the suspect: [name / description / phone, if known].",
      "Lookout notice": "Please be on the lookout for the person using this connection and inform us before taking any action. Description of the suspect: [add details].",
      "Request for assistance": "Please help us identify the subscriber or premises at this location and reply to this station with what you find.",
    };
    setDraft({
      kind,
      subject: `${kind}: TRACE case ${c.ref}`,
      body: `Reference: ${c.ref}, ${st.station || "Cyber Police Station"}.\n\nIn a cyber-fraud complaint under investigation, internet activity was traced to your station's area:\n${facts}\n\n${ask[kind] || ""}\n\nContact: [officer name, phone].`,
    });
    setConfirmed(false);
  }
  const submit = () => run(async () => {
    setNotices(await api.post(`/cases/${c.id}/notices`, { ...draft, recipients, confirmed }));
    setDraft({ kind: "", subject: "", body: "" }); setRcpt({}); setConfirmed(false);
  }, "send");
  const decide = (nid: string, decision: string) => {
    let comment = "";
    if (decision === "return") {
      const why = prompt("Reason for returning this notice to the officer (required):");
      if (why === null) return;
      if (!why.trim()) return setErr("A reason is required to return a notice.");
      comment = why;
    } else if (!confirm(`Approve ${nid} for dispatch? You are confirming the recipients and the message.`)) return;
    run(async () => setNotices(await api.post(`/cases/${c.id}/notices/${nid}/decision`, { decision, comment })), nid);
  };
  const recordDispatch = (nid: string) => {
    const d = dispatch[nid];
    if (!d?.channel) return setErr("Choose how the notice was delivered.");
    run(async () => setNotices(await api.post(`/cases/${c.id}/notices/${nid}/dispatch`, d)), nid);
  };

  const looked = st.pins.filter((p: any) => p.lookup);
  return (
    <>
      <h2>Jurisdiction Lookup</h2>
      <p className="muted">Find the police stations covering the places where IP addresses in the evidence were traced, then prepare a notice to them.</p>
      <div className="note">
        <b>Who decides what</b>
        <ol style={{ margin: "4px 0 0", paddingLeft: 20 }}>
          <li><b>TRACE</b> reads PIN codes from IP trace reports and recommends stations, showing each step of its reasoning. It never chooses recipients or sends anything.</li>
          <li><b>Officer</b> checks the reasoning, chooses the stations, writes the notice and confirms it.</li>
          <li><b>SHO</b> approves the notice or returns it with a reason. Only an approved notice can be dispatched, and the person who delivers it records how.</li>
        </ol>
      </div>
      {!st.online && <div className="note warnbar">Online lookup is switched off on this server. Saved results are shown where they exist.</div>}
      {st.online && !st.google_configured && <div className="note warnbar">No Google Maps key is configured, so lookups can&apos;t be cross-checked and will show as “Not cross-checked”.</div>}

      <h3>1. PIN codes found</h3>
      <table>
        <thead><tr><th></th><th>PIN</th><th>Where it came from</th><th>Activity</th><th>Lookup</th></tr></thead>
        <tbody>
          {st.pins.length ? st.pins.map((p: any) => (
            <tr key={p.pin}>
              <td><input type="checkbox" aria-label={`Select PIN ${p.pin}`} checked={pins.includes(p.pin)}
                onChange={(e) => setPins((x) => (e.target.checked ? [...x, p.pin] : x.filter((y) => y !== p.pin)))} /></td>
              <td className="mono">{p.pin}</td>
              <td>{p.manual ? <span className="muted small">Entered by officer</span>
                : Array.from(new Map(p.traces.map((t: any) => [`${t.src.f}:${t.src.l}`, t.src])).values()).map((s: any, i) => <Chip key={i} s={s} />)}</td>
              <td className="small">{p.traces.map((t: any, i: number) => (
                <div key={i}><span className="mono">{t.ip}</span>{t.at ? ` · ${fmt(t.at)}` : ""}{t.isp ? ` · ${t.isp}` : ""}{t.area ? ` · ${t.area}` : ""}</div>
              ))}</td>
              <td>{p.lookup ? <><Verdict v={p.lookup.verdict} />{p.lookup.cached && <div className="small muted">Saved result, {fmt(p.lookup.looked_up_at)}</div>}</> : <span className="muted small">Not looked up</span>}</td>
            </tr>
          )) : <tr><td colSpan={5} className="muted">No PIN codes yet. Upload an IP trace report in Evidence (a table with IP address and PIN code columns), or enter a PIN below.</td></tr>}
        </tbody>
      </table>
      <div className="row" style={{ marginTop: 8 }}>
        <input placeholder="Add a PIN code (6 digits)" inputMode="numeric" maxLength={6} value={newPin} onChange={(e) => setNewPin(e.target.value.replace(/\D/g, ""))} />
        <button disabled={newPin.length !== 6 || !!busy} onClick={addPin}>Add PIN</button>
        <span style={{ marginLeft: "auto" }} />
        <label className="small"><input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} /> Ignore saved results</label>
        <button className="primary" disabled={!pins.length || !!busy} onClick={lookup}>{busy === "lookup" ? "Looking up…" : `Look up ${pins.length || ""} selected PIN${pins.length === 1 ? "" : "s"}`}</button>
      </div>

      {looked.length > 0 && <>
        <h3>2. TRACE&apos;s reasoning and recommended stations</h3>
        <p className="muted small">Each lookup searches Google Maps for the nearest police station to the PIN, asks the Kerala Police nearby-stations service at those coordinates, and compares the two. Tick the stations you want to notify.</p>
        {looked.map((p: any) => (
          <div className="box" key={p.pin}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <b>PIN {p.pin}{p.traces[0]?.area ? ` · ${p.traces[0].area}` : ""}</b>
              <span><Verdict v={p.lookup.verdict} /> <span className="small muted">{p.lookup.looked_up_at ? `looked up ${fmt(p.lookup.looked_up_at)}` : ""}</span></span>
            </div>
            <ol className="small" style={{ paddingLeft: 20, margin: "6px 0" }}>
              {p.lookup.steps.map((s: any, i: number) => (
                <li key={i}><span className={s.ok ? "ok" : "bad"}>{s.ok ? "✓" : "✗"} {s.step}:</span> {s.detail}</li>
              ))}
            </ol>
            {p.lookup.stations.length ? (
              <table>
                <thead><tr><th>Notify</th><th>Station</th><th>Distance</th><th>Source</th><th>TRACE</th></tr></thead>
                <tbody>{p.lookup.stations.map((s: Station) => {
                  const r: Recipient = { name: s.name, link: s.link, pin: p.pin, source: s.source, recommended: s.recommended };
                  return (
                    <tr key={s.name + s.source}>
                      <td><input type="checkbox" aria-label={`Notify ${s.name}`} checked={!!rcpt[key(r)]} onChange={() => toggle(r)} /></td>
                      <td>{s.link ? <a href={s.link} target="_blank" rel="noreferrer">{s.name}</a> : s.name}</td>
                      <td>{s.distance_km != null ? `${s.distance_km} km` : "—"}</td>
                      <td className="small">{s.source}</td>
                      <td>{s.recommended ? <span className="tag ok">✓ Recommended</span> : <span className="small muted">Not recommended</span>}</td>
                    </tr>
                  );
                })}</tbody>
              </table>
            ) : <p className="muted small">No stations found. Add the station by hand below if you know it.</p>}
          </div>
        ))}
      </>}

      <h3>{looked.length ? "3" : "2"}. Prepare the notice</h3>
      <div className="row">
        <input placeholder="Station name (add by hand)" value={manual.name} onChange={(e) => setManual({ ...manual, name: e.target.value })} />
        <input placeholder="Station page link (optional)" style={{ flex: 1 }} value={manual.link} onChange={(e) => setManual({ ...manual, link: e.target.value })} />
        <select value={manual.pin} onChange={(e) => setManual({ ...manual, pin: e.target.value })}>
          <option value="">PIN (optional)</option>{st.pins.map((p: any) => <option key={p.pin}>{p.pin}</option>)}
        </select>
        <button disabled={!manual.name.trim()} onClick={() => {
          toggle({ name: manual.name.trim(), link: manual.link.trim() || null, pin: manual.pin || null, source: "Entered by officer", recommended: false });
          setManual({ name: "", link: "", pin: "" });
        }}>Add station</button>
      </div>
      <p><b>Recipients:</b> {recipients.length ? recipients.map((r) => (
        <span key={key(r)} className={`tag ${r.recommended ? "ok" : "warn"}`} style={{ marginRight: 4 }}>
          {r.name}{r.pin ? ` · ${r.pin}` : ""} <button className="link" aria-label={`Remove ${r.name}`} onClick={() => toggle(r)}>×</button>
        </span>
      )) : <span className="muted">None chosen yet. Tick stations above or add one by hand.</span>}</p>
      {offRec.length > 0 && <div className="note warnbar">You chose {offRec.map((r) => r.name).join(", ")} outside TRACE&apos;s recommendation. That is your call to make; it will be recorded with the notice and shown to the SHO.</div>}
      <div className="form">
        <label>Type of notice</label>
        <select value={draft.kind} onChange={(e) => fill(e.target.value)}>
          <option value="">Choose…</option>{st.notice_kinds.map((k: string) => <option key={k}>{k}</option>)}
        </select>
        <label>Subject</label>
        <input value={draft.subject} onChange={(e) => { setDraft({ ...draft, subject: e.target.value }); setConfirmed(false); }} />
        <label>Message</label>
        <textarea rows={10} value={draft.body} onChange={(e) => { setDraft({ ...draft, body: e.target.value }); setConfirmed(false); }} />
      </div>
      <p className="small muted">Choosing a type fills in a starting message from the evidence for the chosen stations. Replace the [bracketed] parts and edit freely.</p>
      <p><label><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> I have checked the recipients and the message, and I am responsible for sending this notice.</label></p>
      <p className="err">{err}</p>
      <button className="primary" disabled={!confirmed || !recipients.length || !draft.kind || !draft.body.trim() || !!busy} onClick={submit}>
        {busy === "send" ? "Saving…" : "Send to SHO for approval"}
      </button>

      <h3>Notices for this case</h3>
      <table>
        <thead><tr><th>Notice</th><th>To</th><th>Status</th><th>History</th><th></th></tr></thead>
        <tbody>
          {notices.length ? notices.map((n) => (
            <tr key={n.id}>
              <td><b>{n.id}</b> · {n.kind}<div className="small">{n.subject}</div><div className="mono small">{short(n.sha256)}</div></td>
              <td className="small">{n.recipients.map((r: Recipient) => r.name).join(", ")}
                {n.off_recommendation?.length > 0 && <div className="warn">Outside recommendation: {n.off_recommendation.join(", ")}</div>}</td>
              <td><span className={`tag ${STATUS_CLS[n.status] || ""}`}>{n.status}</span>{n.channel && <div className="small">{n.channel}</div>}</td>
              <td className="small">{(n.history || []).map((h: any, i: number) => (
                <div key={i}>{fmt(h.at)} · {h.by} ({h.role === "sho" ? "SHO" : "Officer"}): {h.step}{h.comment ? ` — “${h.comment}”` : ""}</div>
              ))}</td>
              <td>
                <div className="row">
                  <a className="linkbtn" style={{ textDecoration: "none" }} href={`/api/cases/${c.id}/notices/${n.id}/print`} target="_blank" rel="noreferrer">Print</a>
                  {isSho && n.status === "Awaiting SHO approval" && <>
                    <button className="primary" disabled={!!busy} onClick={() => decide(n.id, "approve")}>Approve</button>
                    <button className="danger" disabled={!!busy} onClick={() => decide(n.id, "return")}>Return</button>
                  </>}
                </div>
                {!isSho && n.status === "Awaiting SHO approval" && <div className="small muted">Waiting for the SHO.</div>}
                {n.status === "Approved for dispatch" && (
                  <div className="row" style={{ marginTop: 6 }}>
                    <select value={dispatch[n.id]?.channel || ""} onChange={(e) => setDispatch({ ...dispatch, [n.id]: { note: dispatch[n.id]?.note || "", channel: e.target.value } })}>
                      <option value="">Delivered by…</option>{st.channels.map((ch: string) => <option key={ch}>{ch}</option>)}
                    </select>
                    <input placeholder="Note (e.g. email ref.)" value={dispatch[n.id]?.note || ""} onChange={(e) => setDispatch({ ...dispatch, [n.id]: { channel: dispatch[n.id]?.channel || "", note: e.target.value } })} />
                    <button disabled={!!busy} onClick={() => recordDispatch(n.id)}>Record dispatch</button>
                  </div>
                )}
              </td>
            </tr>
          )) : <tr><td colSpan={5} className="muted">No notices yet.</td></tr>}
        </tbody>
      </table>
      <p className="small muted">TRACE records notices and keeps a printable copy for each station; it does not deliver them. Every lookup, approval and dispatch is written to the audit trail.</p>
    </>
  );
}
