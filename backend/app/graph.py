"""Neo4j: Gap Hunter's graph. Always a derived view, never the source of truth.

Every Gap Hunter run deletes the case's subgraph and rewrites it from MongoDB
before any Cypher rule runs. A crash mid-rebuild just means the next run
rebuilds again — a half-written graph never feeds a live query
(docs/HACKATHON_PLAN.md §6.4).
"""
import time

from neo4j import GraphDatabase

from app.config import settings

_driver = None
_last_check = (0.0, False)


def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password),
                                       connection_timeout=3)
    return _driver


def neo4j_available() -> bool:
    global _last_check
    if time.time() - _last_check[0] < 15:
        return _last_check[1]
    try:
        get_driver().verify_connectivity()
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    _last_check = (time.time(), ok)
    return ok


def rebuild_case_subgraph(case_id: str, g) -> None:
    """Wipe and rewrite one case's subgraph from the in-memory Graph built from Mongo."""
    by_labels: dict[tuple, list] = {}
    for nid, n in g.nodes.items():
        props = {k: v for k, v in n.items() if k != "labels" and v is not None}
        by_labels.setdefault(tuple(n["labels"]), []).append({**props, "nid": nid, "case_id": case_id})
    by_type: dict[str, list] = {}
    for a, t, b in g.edges:
        by_type.setdefault(t, []).append({"a": a, "b": b})
    def write(tx):  # one transaction: readers never see a half-rebuilt case
        tx.run("MATCH (n {case_id: $cid}) DETACH DELETE n", cid=case_id).consume()
        for labels, rows in by_labels.items():
            tx.run(f"UNWIND $rows AS r CREATE (n:{':'.join(labels)}) SET n = r", rows=rows).consume()
        for t, rows in by_type.items():
            tx.run(f"""UNWIND $rows AS r
                       MATCH (a {{case_id: $cid, nid: r.a}}) MATCH (b {{case_id: $cid, nid: r.b}})
                       CREATE (a)-[:{t}]->(b)""", rows=rows, cid=case_id).consume()

    with get_driver().session() as s:
        s.execute_write(write)


def run_cypher(query: str, **params):
    """Bounded queries only: <= 3 hops, high_degree nodes excluded (§6.4)."""
    with get_driver().session() as s:
        return list(s.run(query, **params))
