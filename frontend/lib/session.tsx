"use client";
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";

/* Malayalam label toggle — labels to be checked by a native speaker (as in the demo). */
const ML: Record<string, string> = {
  cases: "കേസുകൾ", verify: "പരിശോധന", signout: "പുറത്തുകടക്കുക",
  complainant: "പരാതിക്കാർ", evidence: "തെളിവുകൾ", narration: "മൊഴി", analysis: "വിശകലനം", manifest: "തെളിവ് പട്ടിക",
  timeline: "സമയക്രമം", gaps: "വിട്ടുപോയ വിവരങ്ങൾ", draft: "എഫ്ഐആർ കരട്", bns: "ബിഎൻഎസ് വകുപ്പുകൾ",
  referrals: "ഫോറൻസിക് റഫറൽ", jurisdiction: "അധികാരപരിധി", approval: "അംഗീകാരം", export: "എക്സ്പോർട്ട്", audit: "ഓഡിറ്റ്",
};
const EN: Record<string, string> = {
  cases: "Cases", verify: "Verify", signout: "Sign out",
  complainant: "Complainant", evidence: "Evidence", narration: "Narration", analysis: "Analysis", manifest: "Manifest",
  timeline: "Timeline", gaps: "Gap questions", draft: "Draft FIR", bns: "BNS sections", referrals: "Referrals", jurisdiction: "Jurisdiction Lookup",
  approval: "Approval", export: "Export", audit: "Audit trail",
};

export type User = { username: string; name: string; badge: string; role: "officer" | "sho"; role_label: string };
export type Station = { code: string; name: string; demo_accounts: User[] };

type Ctx = {
  user: User | null;
  station: Station | null;
  ready: boolean;
  ml: boolean;
  toggleMl: () => void;
  L: (k: string) => string;
  setUser: (u: User | null) => void;
  logout: (msg?: string) => Promise<void>;
};
const SessionCtx = createContext<Ctx | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [station, setStation] = useState<Station | null>(null);
  const [ready, setReady] = useState(false);
  const [ml, setMl] = useState(false);

  useEffect(() => {
    try { setMl(localStorage.getItem("trace-ml") === "1"); } catch { /* storage blocked */ }
    api.get<Station>("/station").then(setStation).catch(() => {});
    fetch("/api/me", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => setUser(u))
      .finally(() => setReady(true));
  }, []);

  const logout = useCallback(async (msg?: string) => {
    await api.post("/logout").catch(() => {});
    setUser(null);
    if (msg) sessionStorage.setItem("trace-login-msg", msg);
    location.href = "/login";
  }, []);

  // End the session after 15 minutes without activity (the server enforces it too).
  useEffect(() => {
    if (!user) return;
    let last = Date.now();
    const bump = () => { last = Date.now(); };
    const evs = ["mousemove", "keydown", "click"];
    evs.forEach((e) => document.addEventListener(e, bump));
    const t = setInterval(() => { if (Date.now() - last > 15 * 60000) logout("Session ended after 15 minutes of inactivity."); }, 20000);
    return () => { evs.forEach((e) => document.removeEventListener(e, bump)); clearInterval(t); };
  }, [user, logout]);

  const toggleMl = () => setMl((v) => {
    try { localStorage.setItem("trace-ml", v ? "0" : "1"); } catch { /* storage blocked */ }
    return !v;
  });
  const L = (k: string) => (ml ? `${EN[k]} · ${ML[k]}` : EN[k]);

  return <SessionCtx.Provider value={{ user, station, ready, ml, toggleMl, L, setUser, logout }}>{children}</SessionCtx.Provider>;
}

export function useSession() {
  const c = useContext(SessionCtx);
  if (!c) throw new Error("useSession outside provider");
  return c;
}
