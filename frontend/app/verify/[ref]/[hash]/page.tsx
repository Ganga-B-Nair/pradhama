"use client";
import { useParams } from "next/navigation";
import TopBar from "@/components/TopBar";
import VerifyView from "@/components/VerifyView";

/** Target of the QR code on an exported FIR: /verify/<case ref>/<head hash>. Public. */
export default function Page() {
  const { ref, hash } = useParams<{ ref: string; hash: string }>();
  return <><TopBar /><main><VerifyView initialRef={decodeURIComponent(ref)} initialHead={hash} /></main></>;
}
