"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

// TODO(N/G): wire to POST /api/cases, then POST /api/cases/{id}/files for the
// evidence bundle and POST /api/cases/{id}/narration for the audio clip.
// Each uploaded file should show its hash and accepted/rejected status as it
// comes back (PRD US-01, US-02).
export default function NewCasePage() {
  const [name, setName] = useState("");
  const [consent, setConsent] = useState(false);
  const router = useRouter();

  function handleCreate() {
    // placeholder: real version POSTs to /api/cases, then redirects with the real id
    router.push("/cases/c-001");
  }

  return (
    <main className="mx-auto max-w-2xl space-y-4 p-8">
      <h1 className="text-2xl font-semibold">New case — intake</h1>
      <label className="block">
        Complainant name
        <input className="mt-1 w-full rounded border p-2" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        Complainant consents to evidence upload and processing
      </label>
      <div className="rounded border-2 border-dashed p-8 text-center text-slate-400">
        Evidence upload drop zone — TODO(N): multi-file, show hash + status per file as it uploads
      </div>
      <div className="rounded border-2 border-dashed p-8 text-center text-slate-400">
        Voice narration upload — TODO(N): record or upload audio; shows Malayalam + English side by side once transcribed
      </div>
      <button
        className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-40"
        disabled={!name || !consent}
        onClick={handleCreate}
      >
        Create case
      </button>
    </main>
  );
}
