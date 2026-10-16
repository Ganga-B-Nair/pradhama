/**
 * All API calls go through here. USE_MOCK lets N build every screen against
 * mock/*.json before G/V's endpoints are live — see docs/HACKATHON_PLAN.md §7.
 * Flip to false (or set NEXT_PUBLIC_USE_MOCK=false) once an endpoint is real.
 */
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function mockJson<T>(path: string): Promise<T> {
  const res = await fetch(`/mock/${path}`);
  return res.json();
}

async function real<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: "include", ...init });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export const api = {
  login: (username: string, password: string) =>
    USE_MOCK
      ? mockJson("login.json")
      : real("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) }),

  listCases: () => (USE_MOCK ? mockJson("cases.json") : real("/api/cases")),

  startRun: (caseId: string) =>
    USE_MOCK ? mockJson("run_started.json") : real(`/api/cases/${caseId}/runs`, { method: "POST" }),

  getRun: (runId: string) => (USE_MOCK ? mockJson("run_status.json") : real(`/api/runs/${runId}`)),

  getManifest: (caseId: string) => (USE_MOCK ? mockJson("manifest.json") : real(`/api/cases/${caseId}/manifest`)),

  getTimeline: (caseId: string) => (USE_MOCK ? mockJson("timeline.json") : real(`/api/cases/${caseId}/timeline`)),

  getGaps: (caseId: string) => (USE_MOCK ? mockJson("gaps.json") : real(`/api/cases/${caseId}/gaps`)),

  getDraft: (caseId: string) => (USE_MOCK ? mockJson("draft.json") : real(`/api/cases/${caseId}/draft`)),

  getBns: (caseId: string) => (USE_MOCK ? mockJson("bns.json") : real(`/api/cases/${caseId}/bns`)),
};
