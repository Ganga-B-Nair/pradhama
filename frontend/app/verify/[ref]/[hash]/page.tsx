"use client";
import { useEffect, useState } from "react";

// QR codes export encode PUBLIC_BASE_URL + /verify/<ref>/<head_hash>, per
// docs/HACKATHON_PLAN.md §6.6. TODO(N): wire to GET /api/verify/{ref}/{hash}.
export default function VerifyPage({ params }: { params: { ref: string; hash: string } }) {
  const [result, setResult] = useState<string>("checking...");

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}/api/verify/${params.ref}/${params.hash}`)
      .then((r) => r.json())
      .then((data) => setResult(data.result));
  }, [params.ref, params.hash]);

  return (
    <main className="flex min-h-screen items-center justify-center">
      <div className="rounded border bg-white p-8 text-center">
        <div className="text-lg font-medium">Custody chain verification</div>
        <div className={`mt-2 text-2xl ${result === "match" ? "text-green-600" : "text-red-600"}`}>
          {result}
        </div>
      </div>
    </main>
  );
}
