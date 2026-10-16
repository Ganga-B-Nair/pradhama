"""Gap Hunter. docs/HACKATHON_PLAN.md §6.4.

Deterministic graph rules and fixed neutral templates — no LLM anywhere in the
decision path, so the wording is always neutral and can't drift.

Every run deletes the case's subgraph in Neo4j and rewrites it from MongoDB
(Mongo stays the source of truth). Nodes: Case, Person, Phone, Account, UPI,
Event (Transaction events also carry the :Transaction label), File, Statement.
Traversals stay within 3 hops and skip nodes tagged high_degree (> 20 links).
If Neo4j is unreachable the same 6 rules run on an in-memory copy of the
graph, so Gap Hunter degrades instead of blocking the pipeline.
"""
from dataclasses import dataclass, field

from app import custody
from app.agents import extract
from app.db import get_db
from app.graph import neo4j_available, rebuild_case_subgraph, run_cypher
from app.schemas import Gap, checked
from app.util import IST, fmt_ist, money, now_iso, parse_iso

BLOCKED_WORDS = ["lying", "lie", "lied", "liar", "suspicious", "inconsistent story", "credibility", "credible",
                 "deception", "deceptive", "fake", "false complaint", "fabricated", "evasion", "doubtful",
                 "untrue", "contradiction"]
RULES = {
    "G-01": "A payment mentioned in the narration has no supporting financial record.",
    "G-02": "A named person has no phone number, account or address recorded.",
    "G-03": "More than 7 days passed between the last incident event and the report, and no note about this period is recorded.",
    "G-05": "Money went to an account with no bank name or IFSC recorded.",
    "G-07": "A contact (phone or UPI ID) appears in the evidence but not in the narration.",
    "G-09": "The stated total loss differs from the sum of the recorded payments.",
}
SEVERITY = {"G-01": "High", "G-09": "High", "G-05": "High", "G-02": "Medium", "G-07": "Medium", "G-03": "Medium"}
TEMPLATES = {
    "G-01": "The narration mentions a {amount} payment{when}{who}. Is there a bank SMS, statement entry or receipt for this payment?",
    "G-02": "A person named {name} is mentioned, but no phone number, account or address is recorded for them. Which number did {name} use to contact the complainant?",
    "G-03": "The last recorded event is on {last} and the report is on {report}. Is there anything the complainant wants recorded about this period?",
    "G-05": "{amount} went to account {account}{how}, but no bank name or IFSC is recorded for it. Does the complainant have the beneficiary bank details?",
    "G-07": "The {what} {contact} appears in the {where} but not in the narration. Does the complainant recognise this {what}?",
    "G-09": "The stated total loss is {stated}, and the attached records add up to {recorded}. Which payments make up the difference of {diff}?",
}
HIGH_DEGREE = 20


def lint(text: str) -> list[str]:
    import re
    return [w for w in BLOCKED_WORDS if re.search(r"\b" + re.escape(w) + r"\b", text, re.IGNORECASE)]


def render(rule: str, **slots) -> str:
    text = TEMPLATES[rule].format(**slots)
    assert not lint(text), f"blocked word in {rule} question"
    return text


@dataclass
class Graph:
    nodes: dict = field(default_factory=dict)  # id -> {"labels": [...], **props}
    edges: list = field(default_factory=list)  # (from, type, to)

    def node(self, nid: str, labels: list[str], **props):
        if nid not in self.nodes:
            self.nodes[nid] = {"labels": labels, **props}
        return nid

    def edge(self, a: str, t: str, b: str):
        if (a, t, b) not in self.edges:
            self.edges.append((a, t, b))

    def out(self, nid: str, t: str | None = None):
        return [b for a, et, b in self.edges if a == nid and (t is None or et == t)]

    def inc(self, nid: str, t: str | None = None):
        return [a for a, et, b in self.edges if b == nid and (t is None or et == t)]


def build_graph(case_id: str) -> Graph:
    db = get_db()
    case = db.cases.find_one({"id": case_id}) or {}
    analysis = case.get("analysis", {})
    draft = db.drafts.find_one({"case_id": case_id}, sort=[("v", -1)]) or {}
    g = Graph()
    events = list(db.timeline_events.find({"case_id": case_id}, {"_id": 0}))
    last = max((e["at"] for e in events), default=None)
    g.node("case", ["Case"], report_at=case.get("created_at"), last_event_at=last,
           stated_total=analysis.get("stated_total"),
           delay_note=bool((draft.get("fields") or {}).get("delay_reason")))
    g.node("person:complainant", ["Person"], name=case.get("complainant", {}).get("name"), role="complainant")

    files = {f["ev_id"]: f for f in db.files.find({"case_id": case_id, "status": "accepted"})}
    for ev, f in files.items():
        g.node(f"file:{ev}", ["File"], ev_id=ev, kind=f.get("kind"), name=f["name"])
    narration = db.narrations.find_one({"case_id": case_id}) or {}
    for s in narration.get("segments") or []:
        sid = g.node(f"stmt:{s['id']}", ["Statement"], seg=s["id"], text=s.get("en", ""))
        for p in extract.extract_phones(s.get("en", "")):
            g.edge(sid, "MENTIONS", g.node(f"phone:{p}", ["Phone"], value=p))
        for u in extract.extract_upi_ids(s.get("en", "")):
            g.edge(sid, "MENTIONS", g.node(f"upi:{u}", ["UPI"], value=u))
    for name in analysis.get("persons") or []:
        pid = g.node(f"person:{name}", ["Person"], name=name, role="named")
        for s in narration.get("segments") or []:
            if name in s.get("en", ""):
                g.edge(f"stmt:{s['id']}", "MENTIONS", pid)

    all_text = " ".join(s.get("en", "") for s in narration.get("segments") or [])
    for e in events:
        labels = ["Event", "Transaction"] if e["type"] == "Transaction" else ["Event"]
        day = parse_iso(e["at"]).astimezone(IST).date().isoformat() if e["prec"] != "approx" else None
        eid = g.node(f"event:{e['id']}", labels, eid=e["id"], type=e["type"], at=e["at"], amount=e.get("amount"),
                     day=day, narration_only=e["source_kinds"] == ["narration"])
        for s in e["src"]:
            if s.get("f") and s["f"] in files:
                g.edge(eid, "EVIDENCED_BY", f"file:{s['f']}")
            elif s.get("n"):
                g.edge(eid, "STATED_IN", f"stmt:{s['n']}")
        if e.get("to_account"):
            ifsc = e.get("ifsc") or next(iter(extract.extract_ifsc_codes(all_text)), None)
            aid = g.node(f"acct:{e['to_account']}", ["Account"], number=e["to_account"], role="beneficiary", ifsc=None, bank=None)
            if ifsc:
                g.nodes[aid]["ifsc"] = ifsc
            g.edge(eid, "TO_ACCOUNT", aid)
        if e.get("upi"):
            g.edge(eid, "TO_UPI", g.node(f"upi:{e['upi']}", ["UPI"], value=e["upi"]))
        if e.get("phone"):
            g.edge(eid, "WITH_PHONE", g.node(f"phone:{e['phone']}", ["Phone"], value=e["phone"]))
        if e.get("person"):
            g.edge(eid, "INVOLVES", g.node(f"person:{e['person']}", ["Person"], name=e["person"], role="named"))
    # Contact details the officer recorded while answering a gap (e.g. Arun's number).
    for gap in db.gaps.find({"case_id": case_id, "status": "answered", "rule": "G-02"}):
        if extract.extract_phones(gap.get("answer") or "") and gap.get("key"):
            pid = f"person:{gap['key']}"
            if pid in g.nodes:
                g.edge(pid, "HAS_PHONE", g.node(f"phone:{extract.extract_phones(gap['answer'])[0]}", ["Phone"],
                                                value=extract.extract_phones(gap["answer"])[0]))
    degree: dict[str, int] = {}
    for a, _t, b in g.edges:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    for nid, n in g.nodes.items():
        n["high_degree"] = degree.get(nid, 0) > HIGH_DEGREE
    return g


# ------------------------------------------------------------ rules (Cypher)

CYPHER = {
    "G-01": """
        MATCH (e:Transaction {case_id:$cid})-[:STATED_IN]->(:Statement)
        WHERE NOT (e)-[:EVIDENCED_BY]->(:File {kind:'financial_record'})
          AND NOT EXISTS { MATCH (o:Transaction {case_id:$cid, amount:e.amount})-[:EVIDENCED_BY]->(:File {kind:'financial_record'})
                           WHERE e.day IS NULL OR o.day = e.day }
        OPTIONAL MATCH (e)-[:INVOLVES]->(p:Person)
        RETURN e.eid AS eid, e.amount AS amount, e.at AS at, p.name AS person""",
    "G-02": """
        MATCH (p:Person {case_id:$cid, role:'named'})
        WHERE coalesce(p.high_degree,false) = false AND NOT (p)-[:HAS_PHONE|HAS_ACCOUNT]->()
        RETURN p.name AS name""",
    "G-03": """
        MATCH (c:Case {case_id:$cid})
        WHERE c.last_event_at IS NOT NULL AND c.delay_note = false
          AND duration.inSeconds(datetime(c.last_event_at), datetime(c.report_at)).seconds > 7*86400
        RETURN c.last_event_at AS last, c.report_at AS report""",
    "G-05": """
        MATCH (e:Transaction {case_id:$cid})-[:TO_ACCOUNT]->(a:Account {role:'beneficiary'})
        WHERE a.ifsc IS NULL AND a.bank IS NULL AND coalesce(a.high_degree,false) = false
        RETURN a.number AS account, sum(e.amount) AS amount, collect(e.eid) AS eids""",
    "G-07": """
        MATCH (e:Event {case_id:$cid})-[:WITH_PHONE|TO_UPI]->(x)
        WHERE (x:Phone OR x:UPI) AND coalesce(x.high_degree,false) = false
          AND (e)-[:EVIDENCED_BY]->(:File)
          AND NOT (x)<-[:MENTIONS]-(:Statement)
        MATCH (e)-[:EVIDENCED_BY]->(f:File)
        RETURN x.value AS contact, labels(x) AS labels, collect(DISTINCT f.kind) AS kinds, collect(DISTINCT e.eid) AS eids""",
    "G-09": """
        MATCH (c:Case {case_id:$cid}) WHERE c.stated_total IS NOT NULL
        OPTIONAL MATCH (e:Transaction {case_id:$cid})-[:EVIDENCED_BY]->(:File {kind:'financial_record'})
        WITH c, sum(coalesce(e.amount,0)) AS recorded, collect(e.eid) AS eids
        WHERE recorded <> c.stated_total
        RETURN c.stated_total AS stated, recorded, eids""",
}


def _rows_cypher(case_id: str) -> dict:
    return {rule: [dict(r) for r in run_cypher(q, cid=case_id)] for rule, q in CYPHER.items()}


def _rows_memory(g: Graph) -> dict:
    N = g.nodes
    lab = lambda nid, l: l in N[nid]["labels"]  # noqa: E731
    fin = lambda eid: any(N[f]["kind"] == "financial_record" for f in g.out(eid, "EVIDENCED_BY"))  # noqa: E731
    tx = [n for n in N if lab(n, "Transaction")]
    rows = {k: [] for k in CYPHER}
    for e in tx:
        if g.out(e, "STATED_IN") and not fin(e) and not any(N[o]["amount"] == N[e]["amount"] and fin(o) and (N[e]["day"] is None or N[o]["day"] == N[e]["day"]) for o in tx):
            person = next((N[p]["name"] for p in g.out(e, "INVOLVES")), None)
            rows["G-01"].append({"eid": N[e]["eid"], "amount": N[e]["amount"], "at": N[e]["at"], "person": person})
    for p in N:
        if lab(p, "Person") and N[p].get("role") == "named" and not N[p]["high_degree"] and not (g.out(p, "HAS_PHONE") or g.out(p, "HAS_ACCOUNT")):
            rows["G-02"].append({"name": N[p]["name"]})
    c = N["case"]
    if c["last_event_at"] and not c["delay_note"]:
        if (parse_iso(c["report_at"]) - parse_iso(c["last_event_at"])).total_seconds() > 7 * 86400:
            rows["G-03"].append({"last": c["last_event_at"], "report": c["report_at"]})
    for a in N:
        if lab(a, "Account") and N[a].get("role") == "beneficiary" and not N[a]["ifsc"] and not N[a]["bank"] and not N[a]["high_degree"]:
            es = g.inc(a, "TO_ACCOUNT")
            rows["G-05"].append({"account": N[a]["number"], "amount": sum(N[e]["amount"] or 0 for e in es), "eids": [N[e]["eid"] for e in es]})
    for x in N:
        if (lab(x, "Phone") or lab(x, "UPI")) and not N[x]["high_degree"] and not g.inc(x, "MENTIONS"):
            es = [e for e in g.inc(x, "WITH_PHONE") + g.inc(x, "TO_UPI") if g.out(e, "EVIDENCED_BY")]
            if es:
                kinds = sorted({N[f]["kind"] for e in es for f in g.out(e, "EVIDENCED_BY")})
                rows["G-07"].append({"contact": N[x]["value"], "labels": N[x]["labels"], "kinds": kinds, "eids": [N[e]["eid"] for e in es]})
    if c["stated_total"] is not None:
        rec = [e for e in tx if fin(e)]
        recorded = sum(N[e]["amount"] or 0 for e in rec)
        if recorded != c["stated_total"]:
            rows["G-09"].append({"stated": c["stated_total"], "recorded": recorded, "eids": [N[e]["eid"] for e in rec]})
    return rows


WHERE_TXT = {"financial_record": "bank records", "conversation": "chat export", "call_log": "call log", "media": "photographs"}


def questions(rows: dict, events: dict, narration_src: dict) -> list[dict]:
    out = []
    ev_src = lambda eids: [s for eid in eids for s in events.get(eid, {}).get("src", [])]  # noqa: E731
    for r in rows["G-01"]:
        at = parse_iso(r["at"])
        when = f" on {at.astimezone(IST).strftime('%d %B').lstrip('0')}" if at else ""
        out.append({"rule": "G-01", "key": f"{r['amount']:.0f}", "q": render("G-01", amount=money(r["amount"]), when=when,
                    who=f" to a person named {r['person']}" if r.get("person") else ""), "src": ev_src([r["eid"]])})
    for r in rows["G-09"]:
        diff = abs(r["stated"] - r["recorded"])
        src = narration_src.get("total", []) + ev_src(r["eids"])
        out.append({"rule": "G-09", "key": "total", "q": render("G-09", stated=money(r["stated"]), recorded=money(r["recorded"]),
                    diff=money(diff)), "src": src})
    for r in rows["G-05"]:
        hows = {events[e].get("action", "").split(" by ")[1].split(" ")[0] for e in r["eids"] if " by " in events.get(e, {}).get("action", "")}
        out.append({"rule": "G-05", "key": r["account"], "q": render("G-05", amount=money(r["amount"]), account=r["account"],
                    how=f" by {next(iter(hows))}" if len(hows) == 1 else ""), "src": ev_src(r["eids"])})
    for r in rows["G-02"]:
        out.append({"rule": "G-02", "key": r["name"], "q": render("G-02", name=r["name"]), "src": narration_src.get(r["name"], [])})
    for r in rows["G-07"]:
        is_upi = "UPI" in r["labels"]
        contact = r["contact"] if is_upi else extract.pretty_phone(r["contact"])
        where = " and ".join(WHERE_TXT.get(k, "evidence") for k in r["kinds"])
        out.append({"rule": "G-07", "key": r["contact"], "q": render("G-07", what="UPI ID" if is_upi else "phone number",
                    contact=contact, where=where), "src": ev_src(r["eids"])[:4]})
    for r in rows["G-03"]:
        out.append({"rule": "G-03", "key": "delay", "q": render("G-03", last=fmt_ist(r["last"], False), report=fmt_ist(r["report"], False)),
                    "src": []})
    for q in out:
        q["sev"] = SEVERITY[q["rule"]]
    return out


def evaluate(case_id: str) -> tuple[list[dict], str]:
    g = build_graph(case_id)
    engine, rows = "in-memory graph (Neo4j unreachable)", None
    if neo4j_available():
        try:
            rebuild_case_subgraph(case_id, g)
            rows, engine = _rows_cypher(case_id), "Neo4j Cypher"
        except Exception:  # noqa: BLE001 - degrade, never block the pipeline
            rows = None
    if rows is None:
        rows = _rows_memory(g)
    db = get_db()
    events = {e["id"]: e for e in db.timeline_events.find({"case_id": case_id}, {"_id": 0})}
    case = db.cases.find_one({"id": case_id}) or {}
    narration = db.narrations.find_one({"case_id": case_id}) or {}
    nsrc: dict = {}
    for f in case.get("analysis", {}).get("narration_facts") or []:
        if "total" in f.get("kinds", []):
            nsrc.setdefault("total", []).append({"n": f["segment_id"]})
    for name in case.get("analysis", {}).get("persons") or []:
        nsrc[name] = [{"n": s["id"]} for s in narration.get("segments") or [] if name in s.get("en", "")]
    return questions(rows, events, nsrc), engine


def run(case_id: str, user: str = custody.MACHINE) -> str:
    """Open questions are regenerated; answered/dismissed ones are kept. An open
    question whose rule no longer fires (e.g. the missing record was uploaded)
    is closed as answered by the re-check."""
    db = get_db()
    fresh, engine = evaluate(case_id)
    existing = {(x["rule"], x["key"]): x for x in db.gaps.find({"case_id": case_id})}
    fresh_keys = set()
    resolved = []
    for q in fresh:
        k = (q["rule"], q["key"])
        fresh_keys.add(k)
        old = existing.get(k)
        if old:
            upd = {"q": q["q"], "src": q["src"], "sev": q["sev"]}
            if old["status"] == "answered" and old.get("by") == "TRACE (re-check)":
                upd.update(status="open", answer=None, by=None, at=None)
            db.gaps.update_one({"_id": old["_id"]}, {"$set": upd})
        else:
            n = db.gaps.count_documents({"case_id": case_id}) + 1
            db.gaps.insert_one(checked(Gap, {"id": f"q{n}", "case_id": case_id, **q, "status": "open", "answer": None,
                                             "reason": None, "by": None, "at": None, "voice": False}))
    for k, old in existing.items():
        if k not in fresh_keys and old["status"] == "open":
            db.gaps.update_one({"_id": old["_id"]}, {"$set": {
                "status": "answered", "answer": "Resolved on re-check: the rule no longer applies after new information was added.",
                "by": "TRACE (re-check)", "at": now_iso()}})
            resolved.append(old["id"])
    if resolved:
        custody.append(case_id, "GAP_RECHECK_RESOLVED", ", ".join(resolved), custody.MACHINE)
    gaps = list(db.gaps.find({"case_id": case_id}, {"_id": 0}))
    custody.derived(case_id, "gap_questions", gaps, model="none (deterministic rules)", prompt="templates-v1")
    open_n = sum(1 for x in gaps if x["status"] == "open")
    high = sum(1 for x in gaps if x["status"] == "open" and x["sev"] == "High")
    return f"{len(gaps)} questions ({open_n} open, {high} High) via {engine}" + (f"; {len(resolved)} resolved by re-check" if resolved else "")
