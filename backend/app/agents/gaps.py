"""Gap Hunter — owned by V. docs/HACKATHON_PLAN.md §6.4.

Deterministic graph rules, fixed neutral templates. NO LLM in this file's
decision path — that's what keeps the wording non-accusatory and auditable.

Graph: Neo4j, rebuilt from Mongo for the current case only at the start of
every run (app.graph.rebuild_case_subgraph). If Neo4j is unreachable, fall
back to evaluating the same 6 rules against an in-memory rebuild instead of
failing the pipeline (graceful degradation, PRD §1.8).
"""
from neo4j.exceptions import ServiceUnavailable

from app.graph import rebuild_case_subgraph, run_cypher

BLOCKED_WORDS = {"lying", "suspicious", "deceptive", "credibility", "fake", "contradiction"}

RULES = ["G-01", "G-02", "G-03", "G-05", "G-07", "G-09"]

TEMPLATES = {
    # TODO(V): fill in the exact neutral phrasing per rule, e.g. G-03's time-mismatch
    # wording from Trace-QnA.docx §3: "Complainant recalls about {time_a}; the bank
    # record shows {time_b}. Consider gently clarifying the time window."
}


def normalize_entities(case_id: str) -> tuple[list[dict], list[dict]]:
    """Phone -> E.164, UPI -> lowercase, IFSC -> regex-checked. Returns (nodes, edges)
    for app.graph.rebuild_case_subgraph. Nodes with >20 connections get
    props["high_degree"] = True so Cypher rules can exclude them."""
    raise NotImplementedError


def evaluate_rules(case_id: str) -> list[dict]:
    """Runs G-01..G-09 as Cypher, max 3 hops ([*1..3]), skipping high_degree nodes.
    Falls back to an in-memory evaluation if Neo4j is unreachable."""
    try:
        nodes, edges = normalize_entities(case_id)
        rebuild_case_subgraph(case_id, nodes, edges)
    except ServiceUnavailable:
        return _evaluate_rules_in_memory(case_id)
    raise NotImplementedError  # TODO(V): run each rule's Cypher via run_cypher()


def _evaluate_rules_in_memory(case_id: str) -> list[dict]:
    """Fallback path when Neo4j is down — same 6 rules, plain Python over the
    Mongo documents for this case. Never silently skip the check."""
    raise NotImplementedError


def render_question(rule: str, **slots) -> str:
    text = TEMPLATES[rule].format(**slots)
    for word in BLOCKED_WORDS:
        assert word not in text.lower(), f"blocked word '{word}' in gap template output"
    return text


def run(case_id: str) -> None:
    """Entry point called from app.worker._run_stage('gaps', case_id). Also
    called standalone after PATCH /api/gaps/{id} to re-run just this stage."""
    raise NotImplementedError
