"use client";
import RequireUser from "@/components/RequireUser";
import Complainant from "@/components/case/Complainant";

export default function Page() {
  return <RequireUser><Complainant c={null} /></RequireUser>;
}
