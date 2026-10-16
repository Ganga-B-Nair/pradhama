"use client";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useSession, User } from "@/lib/session";

export default function LoginPage() {
  const { station, setUser, user, ready } = useSession();
  const router = useRouter();
  const [username, setUsername] = useState("officer");
  const [password, setPassword] = useState("officer123");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    const m = sessionStorage.getItem("trace-login-msg");
    if (m) { setMsg(m); sessionStorage.removeItem("trace-login-msg"); }
  }, []);
  useEffect(() => { if (ready && user) router.replace("/cases"); }, [ready, user, router]);

  async function signIn(u: string, p: string) {
    try {
      const me = await api.post<User>("/login", { username: u, password: p });
      setUser(me);
      router.push("/cases");
    } catch (e: any) {
      setMsg(e.message);
    }
  }
  const submit = (ev: FormEvent) => { ev.preventDefault(); signIn(username, password); };
  const demoPw: Record<string, string> = { officer: "officer123", sho: "sho123" };

  return (
    <div className="login">
      <h1>TRACE</h1>
      <p className="muted">{station?.name}</p>
      <h2 style={{ marginTop: 24 }}>Sign in</h2>
      <form onSubmit={submit} className="form" style={{ gridTemplateColumns: "110px 1fr" }}>
        <label htmlFor="lu">Username</label>
        <input id="lu" autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} />
        <label htmlFor="lp">Password</label>
        <input id="lp" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <span></span>
        <button className="primary">Sign in</button>
      </form>
      <p className="err">{msg}</p>
      <div className="box">
        <b>Demo direct sign-in</b>
        <p className="muted small">Demo passwords: <code>officer123</code> and <code>sho123</code>. Five wrong passwords lock an account for 15 minutes.</p>
        <div className="row">
          {station?.demo_accounts.map((u) => (
            <button key={u.username} onClick={() => signIn(u.username, demoPw[u.username])}>{u.role_label} · {u.name}</button>
          ))}
        </div>
      </div>
      <p><button className="link" onClick={() => router.push("/verify")}>Verify an exported record</button></p>
    </div>
  );
}
