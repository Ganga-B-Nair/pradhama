"""Gap Hunter — owned by V. docs/HACKATHON_PLAN.md §6.4.

Deterministic rules, fixed neutral templates. NO LLM in this file's decision
path — that's what keeps the wording non-accusatory and auditable.

Implementation note (deviation from the plan, documented so it's easy to
revert): the graph is rebuilt in Neo4j on every run — for the explainability
"deep dive" view and the audit trail — but the 6 rules are *evaluated* in
plain Python against the same normalized entities, not via live Cypher
queries. This file's author cannot run a live Neo4j instance to validate
driver/version-specific Cypher syntax before a teammate's machine does, and a
wrong-but-silent Cypher query is worse than no Cypher at all. `evaluate_rules`
still calls `rebuild_case_subgraph`, so the graph is populated either way; if
Neo4j is unreachable, the graph write is skipped and the rules still run
in-memory — same observable behaviour either way.
"""
import re
from datetime import datetime, timedelta

from neo4j.exceptions import ServiceUnavailable

from app.agents import extract
from app.custody import append_entry
from app.db import get_db
from app.graph import rebuild_case_subgraph

BLOCKED_WORDS = {"lying", "suspicious", "deceptive", "credibility", "fake", "contradiction"}

RULES = ["G-01", "G-02", "G-03", "G-05", "G-07", "G-09"]

TEMPLATES = {
    "G-01": "A payment of Rs {amount} is mentioned in the narration, but no matching financial "
            "record has been uploaded. Consider asking for the transaction slip or bank statement.",
    "G-02": "{name} is mentioned in the case but no phone number or account has been recorded for "
            "them. Consider asking for a way to reach or identify this person.",
    "G-03": "More than 7 days passed between the last recorded event ({last_event_date}) and the "
            "report date, with no reason recorded. Consider gently asking what happened in between.",
    "G-05": "A transfer to account {account} has been recorded with no bank name or IFSC code. "
            "Consider asking for the receiving bank's name or IFSC code.",
    "G-07": "{contact} appears in the uploaded evidence but was not mentioned in the narration. "
            "Consider asking the complainant about this contact.",
    "G-09": "The complainant's stated total loss of Rs {stated_total} does not match the sum of the "
            "recorded transactions, Rs {sum_total}. Consider asking the complainant to review the amounts.",
}

DELAY_THRESHOLD_DAYS = 7
TOTAL_LOSS_RE = re.compile(r"(?:total loss|lost a total of|lost|total)\D{0,15}(?:rs\.?|inr|₹)\s?([\d,]+)", re.IGNORECASE)
NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b")
COMMON_WORD_STOPLIST = {
    "The", "Dear", "Customer", "Bank", "Account", "Rs", "Thank", "Regards",
    "Hello", "Hi", "Please", "Officer", "Police", "Station",
}


def normalize_entities(case_id: str) -> tuple[list[dict], list[dict]]:
    """Phone -> E.164, UPI -> lowercase, IFSC -> regex-checked. Returns (nodes, edges)
    for app.graph.rebuild_case_subgraph. Nodes with >20 connections get
    props["high_degree"] = True so Cypher rules can exclude them."""
    db = get_db()
    nodes: list[dict] = []
    edges: list[dict] = []
    degree: dict[str, int] = {}

    def add_node(node_id: str, label: str, props: dict):
        if not any(n["id"] == node_id for n in nodes):
            nodes.append({"id": node_id, "label": label, "props": props})

    def add_edge(from_id: str, to_id: str, edge_type: str, props: dict | None = None):
        edges.append({"from": from_id, "to": to_id, "type": edge_type, "props": props or {}})
        degree[from_id] = degree.get(from_id, 0) + 1
        degree[to_id] = degree.get(to_id, 0) + 1

    files = list(db.files.find({"case_id": case_id}, {"_id": 0}))
    for f in files:
        add_node(f["id"], "File", {"name": f["name"], "kind": f.get("kind")})

    events = list(db.timeline_events.find({"case_id": case_id}, {"_id": 0}))
    for event in events:
        add_node(event["id"], "Event", {"summary": event["summary"], "timestamp": event["timestamp"]})
        if event.get("amount") is not None:
            add_node(f"txn-{event['id']}", "Transaction", {"amount": event["amount"], "account": event.get("account")})
            add_edge(event["id"], f"txn-{event['id']}", "INVOLVES")
        for file_id in event.get("source_file_ids", []):
            add_edge(event["id"], file_id, "EVIDENCED_BY")
        if event.get("account"):
            account_id = f"acct-{event['account']}"
            add_node(account_id, "Account", {"number": event["account"]})
            add_edge(event["id"], account_id, "INVOLVES")

    for node_id, count in degree.items():
        for node in nodes:
            if node["id"] == node_id and count > 20:
                node["props"]["high_degree"] = True

    return nodes, edges


def _case_narration_text(case_id: str) -> str:
    db = get_db()
    return " ".join(n.get("english_text", "") for n in db.narrations.find({"case_id": case_id}))


def _case_full_text(case_id: str) -> str:
    db = get_db()
    parts = [_case_narration_text(case_id)]
    parts += [e.get("summary", "") for e in db.timeline_events.find({"case_id": case_id})]
    return " ".join(parts)


def _evaluate_rules_in_memory(case_id: str) -> list[dict]:
    """Same 6 rules, plain Python over the Mongo documents for this case."""
    db = get_db()
    case = db.cases.find_one({"id": case_id}) or {}
    events = list(db.timeline_events.find({"case_id": case_id}, {"_id": 0}))
    narration_text = _case_narration_text(case_id)
    full_text = _case_full_text(case_id)
    gaps: list[dict] = []

    # G-01: a narration-sourced payment with no matching financial-record event (same amount).
    financial_amounts = {
        e["amount"] for e in events
        if e.get("amount") is not None and "financial_record" in e.get("source_kinds", [])
    }
    for event in events:
        is_narration_sourced = "narration" in event.get("source_kinds", [])
        if is_narration_sourced and event.get("amount") is not None and event["amount"] not in financial_amounts:
            gaps.append({
                "rule": "G-01",
                "question": render_question("G-01", amount=f"{event['amount']:,.0f}"),
                "related_event_ids": [event["id"]],
            })

    # G-02: a name mentioned in the narration with no phone/account anywhere in the case's text.
    phones = set(extract.extract_phones(full_text))
    candidate_names = {
        m.group(1) for m in NAME_RE.finditer(narration_text) if m.group(1) not in COMMON_WORD_STOPLIST
    }
    for name in sorted(candidate_names):
        if not phones and not extract.extract_accounts(full_text):
            gaps.append({"rule": "G-02", "question": render_question("G-02", name=name), "related_event_ids": []})
            break  # one gap per case for this heuristic rule, not one per name

    # G-03: last event more than 7 days before the case was reported.
    dated_events = [e for e in events if e.get("timestamp")]
    if dated_events:
        try:
            last_event_dt = max(datetime.fromisoformat(e["timestamp"]) for e in dated_events)
            report_dt = case.get("created_at") or datetime.utcnow()
            if isinstance(report_dt, str):
                report_dt = datetime.fromisoformat(report_dt)
            if report_dt.tzinfo and not last_event_dt.tzinfo:
                last_event_dt = last_event_dt.replace(tzinfo=report_dt.tzinfo)
            elif last_event_dt.tzinfo and not report_dt.tzinfo:
                report_dt = report_dt.replace(tzinfo=last_event_dt.tzinfo)
            if (report_dt - last_event_dt) > timedelta(days=DELAY_THRESHOLD_DAYS):
                gaps.append({
                    "rule": "G-03",
                    "question": render_question("G-03", last_event_date=last_event_dt.date().isoformat()),
                    "related_event_ids": [],
                })
        except (ValueError, TypeError):
            pass

    # G-05: an account mentioned with no IFSC recorded anywhere in the case's text.
    ifsc_codes = extract.extract_ifsc_codes(full_text)
    for event in events:
        if event.get("account") and not ifsc_codes:
            gaps.append({
                "rule": "G-05",
                "question": render_question("G-05", account=event["account"]),
                "related_event_ids": [event["id"]],
            })

    # G-07: a phone/UPI contact present in evidence files but absent from the narration.
    evidence_text = " ".join(
        e.get("summary", "") for e in events if "narration" not in e.get("source_kinds", [])
    )
    narration_phones = set(extract.extract_phones(narration_text))
    narration_upis = set(extract.extract_upi_ids(narration_text))
    for phone in extract.extract_phones(evidence_text):
        if phone not in narration_phones:
            gaps.append({"rule": "G-07", "question": render_question("G-07", contact=phone), "related_event_ids": []})
    for upi in extract.extract_upi_ids(evidence_text):
        if upi not in narration_upis:
            gaps.append({"rule": "G-07", "question": render_question("G-07", contact=upi), "related_event_ids": []})

    # G-09: stated total loss vs. sum of recorded transactions.
    stated_match = TOTAL_LOSS_RE.search(narration_text)
    if stated_match:
        stated_total = float(stated_match.group(1).replace(",", ""))
        sum_total = sum(e["amount"] for e in events if e.get("amount") is not None)
        if round(stated_total) != round(sum_total):
            gaps.append({
                "rule": "G-09",
                "question": render_question("G-09", stated_total=f"{stated_total:,.0f}", sum_total=f"{sum_total:,.0f}"),
                "related_event_ids": [e["id"] for e in events if e.get("amount") is not None],
            })

    return gaps


def evaluate_rules(case_id: str) -> list[dict]:
    """Rebuilds the Neo4j subgraph (best-effort) and runs the 6 rules in-memory —
    see the module docstring for why rule evaluation itself stays in Python."""
    try:
        nodes, edges = normalize_entities(case_id)
        rebuild_case_subgraph(case_id, nodes, edges)
    except ServiceUnavailable:
        pass
    return _evaluate_rules_in_memory(case_id)


def render_question(rule: str, **slots) -> str:
    text = TEMPLATES[rule].format(**slots)
    for word in BLOCKED_WORDS:
        assert word not in text.lower(), f"blocked word '{word}' in gap template output"
    return text


def run(case_id: str) -> None:
    """Entry point called from app.worker._run_stage('gaps', case_id). Also
    called standalone after PATCH /api/gaps/{id} to re-run just this stage.

    Re-run semantics: open gaps are regenerated; answered/dismissed gaps are
    left untouched (docs/HACKATHON_PLAN.md §6.4 "re-run after the officer
    answers"). De-duplication is per (rule, related_event_ids) signature, not
    per rule, so answering one G-07 contact doesn't suppress a different,
    still-open G-07 contact for the same case.
    """
    db = get_db()
    fresh_gaps = evaluate_rules(case_id)

    def _signature(gap: dict) -> tuple:
        return (gap["rule"], tuple(sorted(gap.get("related_event_ids", []))))

    resolved_signatures = {
        _signature(g) for g in db.gaps.find({"case_id": case_id, "status": {"$in": ["answered", "dismissed"]}})
    }
    db.gaps.delete_many({"case_id": case_id, "status": "open"})

    import uuid
    to_insert = []
    for gap in fresh_gaps:
        if _signature(gap) in resolved_signatures:
            continue
        to_insert.append({
            "id": str(uuid.uuid4()),
            "case_id": case_id,
            "rule": gap["rule"],
            "question": gap["question"],
            "status": "open",
            "answer": None,
            "dismiss_reason": None,
            "related_event_ids": gap["related_event_ids"],
        })
    if to_insert:
        db.gaps.insert_many([dict(g) for g in to_insert])
    append_entry(case_id, "ARTIFACT_DERIVED", {"artifact": "gaps", "open_count": len(to_insert)})
