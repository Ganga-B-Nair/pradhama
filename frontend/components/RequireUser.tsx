"use client";
import { ReactNode, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";
import TopBar from "./TopBar";

export default function RequireUser({ children, bare }: { children: ReactNode; bare?: boolean }) {
  const { user, ready } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);
  if (!ready || !user) return <main className="muted">Loading…</main>;
  return (
    <>
      <TopBar />
      {bare ? children : <main>{children}</main>}
    </>
  );
}
