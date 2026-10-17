"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmt, money } from "@/lib/util";
import { Chips } from "./bits";
import { useCase } from "./ctx";

export default function Timeline() {
  const { c } = useCase();
  const [events, setEvents] = useState<any[] | null>(null);
  const [f, setF] = useState<any>({});
  const [hl, setHl] = useState<string | null>(null);
  useEffect(() => { api.get(`/cases/${c.id}/timeline`).then((r) => setEvents(r.events)); }, [c.id]);
  if (!events) return <><h2>Timeline</h2><p className="muted">Loading…</p></>;
  if (!events.length) return <><h2>Timeline</h2><p className="muted">No events yet. Run analysis to build the timeline.</p></>;

  const istDay = (iso: string) => new Date(new Date(iso).getTime() + 330 * 60000).toISOString().slice(0, 10);
  const days = Array.from(new Set(events.map((e) => istDay(e.at)))).sort();
  let ev = events.slice().sort((a, b) => a.at.localeCompare(b.at));
  if (f.day) ev = ev.filter((e) => istDay(e.at) === f.day);
  if (f.etype) ev = ev.filter((e) => e.type === f.etype);
  if (f.person) ev = ev.filter((e) => e.actor === f.person);
  const types = Array.from(new Set(events.map((e) => e.type)));
  const people = Array.from(new Set(events.map((e) => e.actor)));

  let svg = null;
  if (ev.length) {
    const ts = ev.map((e) => Date.parse(e.at)), lo = Math.min(...ts), hi = Math.max(...ts);
    const X = (t: number) => (hi === lo ? 500 : 30 + ((t - lo) / (hi - lo)) * 940);
    const clamp = (x: number, a: number, b: number) => Math.max(a, Math.min(b, x));
    const ticks = f.day
      ? [0, 6, 12, 18, 24].map((h) => Date.parse(f.day + "T00:00:00+05:30") + h * 3600000).filter((t) => t >= lo - 3600000 && t <= hi + 3600000)
      : Array.from(new Set(ev.map((e) => istDay(e.at)))).map((d) => Date.parse(d + "T00:00:00+05:30")).filter((t) => t >= lo - 864e5);
    svg = <>
      <svg viewBox="0 0 1000 70" style={{ width: "100%", height: "auto", border: "1px solid var(--line)", borderRadius: 4 }} role="img" aria-label="Event timeline">
        <line x1="20" x2="980" y1="30" y2="30" stroke="#9aa3ad" />
        {ticks.map((t) => <g key={t}>
          <line x1={clamp(X(t), 20, 980)} x2={clamp(X(t), 20, 980)} y1="24" y2="36" stroke="#9aa3ad" />
          <text x={clamp(X(t), 24, 940)} y="56">{fmt(new Date(t).toISOString(), !!f.day).replace(/, \d{4}/, "").replace(/ \d{4}/, "")}</text>
        </g>)}
        {ev.map((e) => (
          <circle key={e.id} cx={X(Date.parse(e.at))} cy="30" r="6" fill={e.prec === "exact" ? "#000000" : "#fff"} stroke="#000000" strokeWidth="2" style={{ cursor: "pointer" }}
            onClick={() => { setHl(e.id); document.getElementById("ev-" + e.id)?.scrollIntoView({ block: "center" }); }}>
            <title>{fmt(e.at)} · {e.action}</title>
          </circle>
        ))}
      </svg>
      <p className="muted small">Filled dot: exact time. Hollow dot: date only or approximate.</p>
    </>;
  }

  return (
    <>
      <h2>Timeline</h2>
      <div className="row" style={{ marginBottom: 8 }}>
        <label>Zoom <select value={f.day || ""} onChange={(e) => setF({ ...f, day: e.target.value })}><option value="">All days</option>{days.map((d) => <option key={d} value={d}>{fmt(d + "T12:00:00+05:30", false)}</option>)}</select></label>
        <select value={f.etype || ""} onChange={(e) => setF({ ...f, etype: e.target.value })}><option value="">All event types</option>{types.map((t) => <option key={t}>{t}</option>)}</select>
        <select value={f.person || ""} onChange={(e) => setF({ ...f, person: e.target.value })}><option value="">All people</option>{people.map((p) => <option key={p}>{p}</option>)}</select>
      </div>
      {svg}
      <table style={{ marginTop: 10 }}>
        <thead><tr><th>Time (IST)</th><th>Precision</th><th>Who</th><th>What</th><th>Amount</th><th>Place</th><th>Confidence</th><th>Sources</th></tr></thead>
        <tbody>
          {ev.length ? ev.map((e) => (
            <tr key={e.id} id={`ev-${e.id}`} className={hl === e.id ? "hl" : ""}>
              <td>{e.prec === "exact" ? fmt(e.at) : fmt(e.at, false)}</td>
              <td>{e.prec === "exact" ? "Exact" : e.prec === "day" ? "Date only" : "Approximate"}</td>
              <td>{e.actor}</td><td>{e.action}{e.url ? <div className="small mono">{e.url}</div> : null}</td>
              <td>{e.amount ? money(e.amount) : ""}</td><td>{e.place || ""}</td><td>{Math.round(e.conf * 100)}%</td>
              <td><Chips src={e.src} /></td>
            </tr>
          )) : <tr><td colSpan={8} className="muted">No events match the filters.</td></tr>}
        </tbody>
      </table>
      <p className="muted small">Every event has at least one source. Events found in several sources are merged and show all of them. Narration-only events carry lower confidence.</p>
    </>
  );
}
