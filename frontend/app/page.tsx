"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";

export default function Home() {
  const { user, ready } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (ready) router.replace(user ? "/cases" : "/login");
  }, [ready, user, router]);
  return <main className="muted">Loading…</main>;
}
