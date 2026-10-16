"use client";
import { ReactNode, useEffect } from "react";
import { cap, tc } from "@/lib/util";
import { Src, useCase } from "./ctx";

export function StatusTag({ s }: { s: string }) {
  const cls = s === "review" ? "warn" : s === "approved" || s === "exported" ? "ok" : "";
  return <span className={`tag ${cls}`}>{cap(s)}</span>;
}

export function Chip({ s }: { s: Src }) {
  const { segments, openSrc } = useCase();
  let label: string;
  if (s.n) {
    const seg = segments.find((x) => x.id === s.n);
    label = seg && seg.end ? `Narration ${tc(seg.t)}` : `Narration #${s.n}`;
  } else label = s.l ? `${s.f} line ${s.l}` : s.l === 0 ? `${s.f} EXIF` : `${s.f}`;
  return <button className="chip" onClick={() => openSrc(s)}>{label}</button>;
}

export function Chips({ src }: { src: Src[] }) {
  return <>{src.map((s, i) => <Chip key={i} s={s} />)}</>;
}

export function Modal({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-bg" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal">
        {children}
        <p style={{ textAlign: "right" }}><button onClick={onClose}>Close</button></p>
      </div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <><h2>{title}</h2><p className="muted">{children}</p></>;
}
