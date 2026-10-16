"use client";
import { usePathname, useRouter } from "next/navigation";
import { useSession } from "@/lib/session";

export default function TopBar() {
  const { user, station, ml, toggleMl, L, logout } = useSession();
  const router = useRouter();
  const path = usePathname();
  if (!user) return null;
  const nav: [string, string][] = [["/cases", L("cases")], ["/verify", L("verify")]];
  return (
    <header className="top">
      <b>TRACE</b>
      <span className="muted">{station?.name}</span>
      <nav>
        {nav.map(([href, label]) => (
          <button key={href} className={path.startsWith(href) ? "on" : ""} onClick={() => router.push(href)}>{label}</button>
        ))}
      </nav>
      <span className="right">
        <span>{user.name} · {user.role_label}</span>
        <button onClick={toggleMl} title="Show Malayalam labels">{ml ? "English labels" : "മലയാളം labels"}</button>
        <button onClick={() => logout()}>{L("signout")}</button>
      </span>
    </header>
  );
}
