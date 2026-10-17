export const fmt = (iso?: string | null, time = true) =>
  iso
    ? new Date(iso).toLocaleString("en-GB", {
        timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric",
        ...(time ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
      })
    : "";
export const short = (h?: string | null) => (h ? h.slice(0, 10) + "…" + h.slice(-6) : "");
export const money = (n: number) => "₹" + Number(n).toLocaleString("en-IN");
export const kb = (n: number) => (n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");
export const tc = (t: number) => String(Math.floor(t / 60)).padStart(2, "0") + ":" + String(Math.floor(t % 60)).padStart(2, "0");
export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function toast(msg: string) {
  const d = document.createElement("div");
  d.textContent = msg;
  d.className = "toast";
  document.body.appendChild(d);
  setTimeout(() => d.remove(), 1800);
}

export function copyText(t: string) {
  if (navigator.clipboard) navigator.clipboard.writeText(t).then(() => toast("Copied"), () => prompt("Copy:", t));
  else prompt("Copy:", t);
}

export function download(name: string, text: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export const csv = (rows: unknown[][]) =>
  rows.map((r) => r.map((v) => (/[",\n]/.test(String(v ?? "")) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v ?? ""))).join(",")).join("\n");

export const KIND_LABEL: Record<string, string> = {
  financial_record: "Financial record", ip_trace: "IP trace report", conversation: "Conversation", media: "Media", call_log: "Call log", audio: "Audio", other: "Other",
};
export const SCREEN_TXT: Record<string, string> = {
  none: "No screening concern", review: "Recommend forensic review", not: "Not screened", na: "Not applicable",
};
