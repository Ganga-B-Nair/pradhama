"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type Case = { id: string; complainant_name: string; status: string; created_at: string };

export default function CaseListPage() {
  const [cases, setCases] = useState<Case[]>([]);

  useEffect(() => {
    api.listCases().then((data: any) => setCases(data));
  }, []);

  return (
    <main className="mx-auto max-w-3xl p-8">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Cases</h1>
        <Link href="/cases/new" className="rounded bg-slate-900 px-4 py-2 text-white">
          + New case
        </Link>
      </div>
      <ul className="space-y-2">
        {cases.map((c) => (
          <li key={c.id}>
            <Link href={`/cases/${c.id}`} className="block rounded border bg-white p-4 hover:bg-slate-50">
              <div className="font-medium">{c.complainant_name}</div>
              <div className="text-sm text-slate-500">
                {c.status} · {new Date(c.created_at).toLocaleString()}
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {/* TODO(N): empty state when cases.length === 0 */}
    </main>
  );
}
