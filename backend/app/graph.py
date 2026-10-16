"""Neo4j: Gap Hunter's graph. Always a derived view, never the source of truth.

Every run, the worker deletes the current case's subgraph and rewrites it from
MongoDB documents before running any Cypher rule. This is what avoids dual-write
drift: a crash mid-rebuild just means the next run rebuilds again from Mongo,
never a half-written graph feeding a live query (see docs/HACKATHON_PLAN.md §6.4).

If Neo4j is unreachable, callers should catch ServiceUnavailable and fall back
to the in-memory rule evaluation path (see agents/gaps.py) rather than failing
the whole pipeline run.
"""
from neo4j import GraphDatabase

from app.config import settings

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
    return _driver


def rebuild_case_subgraph(case_id: str, nodes: list[dict], edges: list[dict]) -> None:
    """Wipe and rewrite one case's subgraph from normalized Mongo data.

    nodes: [{"id": str, "label": str, "props": dict}]
    edges: [{"from": str, "to": str, "type": str, "props": dict}]
    Generic/high-degree entities (e.g. a shared bank branch code) should already
    be tagged `high_degree: true` in props by the caller, before they reach here.
    """
    driver = get_driver()
    with driver.session() as session:
        session.run("MATCH (n {case_id: $case_id}) DETACH DELETE n", case_id=case_id)
        for node in nodes:
            session.run(
                f"CREATE (n:{node['label']} $props)",
                props={**node["props"], "id": node["id"], "case_id": case_id},
            )
        for edge in edges:
            session.run(
                f"""
                MATCH (a {{id: $from_id, case_id: $case_id}})
                MATCH (b {{id: $to_id, case_id: $case_id}})
                CREATE (a)-[r:{edge['type']} $props]->(b)
                """,
                from_id=edge["from"],
                to_id=edge["to"],
                case_id=case_id,
                props=edge.get("props", {}),
            )


def run_cypher(query: str, **params):
    """Run a bounded Cypher query. Callers must keep traversals to <=3 hops and
    exclude nodes tagged high_degree, per docs/HACKATHON_PLAN.md §6.4."""
    driver = get_driver()
    with driver.session() as session:
        return list(session.run(query, **params))
