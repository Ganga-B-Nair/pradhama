"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const [username, setUsername] = useState("officer");
  const [password, setPassword] = useState("officer123");
  const router = useRouter();

  async function handleLogin() {
    await api.login(username, password);
    router.push("/cases");
  }

  return (
    <main className="flex min-h-screen items-center justify-center">
      <div className="w-80 space-y-4 rounded-lg border bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold">TRACE — Station Login</h1>
        <input
          className="w-full rounded border p-2"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="officer or sho"
        />
        <input
          className="w-full rounded border p-2"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="w-full rounded bg-slate-900 p-2 text-white" onClick={handleLogin}>
          Log in
        </button>
      </div>
    </main>
  );
}
