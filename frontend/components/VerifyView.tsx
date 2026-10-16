"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { fmt } from "@/lib/util";

export default function VerifyView({ initialRef = "", initialHead = "" }: { initialRef?: string; initialHead?: string }) {
  const { user } = useSession();
  const router = useRouter();
  const [ref, setRef] = useState(initialRef);
  const [head, setHead] = useState(initialHead);
  const [r, setR] = useState<any>(null);

  async function run(rf = ref, hd = head) {
    if (!rf.trim() || !hd.trim()) return;
    setR(await api.get(`/verify/${encodeURIComponent(rf.trim())}/${hd.trim().toLowerCase()}`).catch((e) => ({ result: "error", message: e.message })));
  }
  useEffect(() => { if (initialRef && initialHead) run(initialRef, initialHead); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <h2>Verify an exported record</h2>
      <p className="muted">Opened from the QR code on an exported FIR. Shows only whether the record matches; no case content. Available on the police network only.</p>
      <div className="form" style={{ gridTemplateColumns: "140px 1fr" }}>
        <label>Case reference</label><input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="KCPS-2026-00001" />
        <label>Head hash</label><input className="mono" value={head} onChange={(e) => setHead(e.target.value)} placeholder="64 hex characters" />
        <span></span>
        <div className="row"><button className="primary" onClick={() => run()}>Verify</button>{!user && <button onClick={() => router.push("/login")}>Back to sign in</button>}</div>
      </div>
      {r && (
        <div className="box" style={{ marginTop: 12 }}>
          {r.result === "match" ? <>
            <p className="ok"><b>Match.</b> The audit chain is intact up to this record.</p>
            <p>Case {r.ref} · export {r.export_version ? "v" + r.export_version : "(not an export entry)"} · entry #{r.seq} on {fmt(r.at)}</p>
            <p>Originals: {r.files_ok} of {r.files_checked} re-hashed from storage and match.</p>
          </> : r.result === "mismatch" ? (
            <p className="bad"><b>Mismatch at entry #{r.seq}.</b> {fmt(r.at)} · {r.action}. The audit chain has been altered at or before this entry.</p>
          ) : <p className="bad"><b>{r.result === "not_found" ? "No match." : "Error."}</b> {r.message}</p>}
        </div>
      )}
    </>
  );
}
