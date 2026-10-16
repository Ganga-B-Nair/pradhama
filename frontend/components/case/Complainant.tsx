"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { fmt, toast } from "@/lib/util";
import { useCaseMaybe } from "./ctx";

const CONSENT = {
  v: "CN-1.0",
  en: "The information and files you give will be used by the police only to record and investigate this complaint. Files are stored inside the police station's system. Text from your statement may be processed by an AI service running inside the station. You can ask what has been recorded.",
  ml: "നിങ്ങൾ നൽകുന്ന വിവരങ്ങളും ഫയലുകളും ഈ പരാതി രേഖപ്പെടുത്താനും അന്വേഷിക്കാനും മാത്രമേ പോലീസ് ഉപയോഗിക്കൂ. ഫയലുകൾ പോലീസ് സ്റ്റേഷന്റെ സിസ്റ്റത്തിനുള്ളിൽ സൂക്ഷിക്കും. നിങ്ങളുടെ മൊഴിയുടെ വാചകം സ്റ്റേഷനുള്ളിൽ പ്രവർത്തിക്കുന്ന ഒരു AI സേവനം പ്രോസസ്സ് ചെയ്തേക്കാം. രേഖപ്പെടുത്തിയ വിവരങ്ങൾ എന്താണെന്ന് നിങ്ങൾക്ക് ചോദിച്ചറിയാം.",
};

export default function Complainant({ c: forced }: { c?: null }) {
  const ctx = useCaseMaybe();
  const router = useRouter();
  const c = forced === null ? null : ctx?.c ?? null;
  const isNew = !c;
  const p = c ? c.complainant : { name: "", contact: "", address: "", language: "Malayalam" };
  const ed = isNew || !!ctx?.canEdit;
  const [v, setV] = useState({ name: p.name, contact: p.contact, address: p.address, language: p.language });
  const [consent, setConsent] = useState(false);
  const [err, setErr] = useState("");
  const set = (k: string) => (e: any) => setV({ ...v, [k]: e.target.value });

  async function save() {
    if (!v.name.trim()) return setErr("Name is required.");
    if (isNew && !consent) return setErr("Record consent before saving a new case.");
    try {
      if (isNew) {
        const created = await api.post("/cases", { ...v, consent });
        router.push(`/cases/${created.id}?tab=evidence`);
      } else {
        await api.put(`/cases/${c.id}/complainant`, { ...v, consent: true });
        await ctx!.reload();
        toast("Saved");
      }
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <>
      <h2>{isNew ? "New case · " : ""}Complainant and consent</h2>
      {isNew && <p className="muted">The case reference is created when you save. Evidence upload unlocks after consent is recorded.</p>}
      <div className="form">
        <label>Name</label><input value={v.name} onChange={set("name")} disabled={!ed} />
        <label>Contact number</label><input value={v.contact} onChange={set("contact")} disabled={!ed} />
        <label>Address</label><input value={v.address} onChange={set("address")} disabled={!ed} />
        <label>Preferred language</label>
        <select value={v.language} onChange={set("language")} disabled={!ed}><option>Malayalam</option><option>English</option></select>
      </div>
      <h3>Consent notice <span className="muted small">version {CONSENT.v}</span></h3>
      <div className={`box ${v.language === "Malayalam" ? "ml" : ""}`}>{v.language === "Malayalam" ? CONSENT.ml : CONSENT.en}</div>
      {c?.complainant.consent_at ? (
        <p className="ok">Consent recorded on {fmt(c.complainant.consent_at)} (notice {c.complainant.consent_version}).</p>
      ) : (
        <label className="row"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} disabled={!ed} /> The notice was read out to the complainant in {v.language} and they agreed.</label>
      )}
      <p className="err">{err}</p>
      {ed && (
        <div className="row">
          <button className="primary" onClick={save}>Save</button>
          {isNew && <button onClick={() => router.push("/cases")}>Cancel</button>}
        </div>
      )}
    </>
  );
}
