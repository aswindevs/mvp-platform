from __future__ import annotations

import json
import logging
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException

from .db import execute_cypher_multi, execute_cypher

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/agents")
def list_agents():
    """Return all Agent nodes with their owning Identity."""
    query = """
        MATCH (i:Identity)-[:owns]->(a:Agent)
        RETURN a, i
    """
    try:
        rows = execute_cypher_multi(query, ["agent", "identity"])
    except Exception:
        logger.exception("Failed to list agents")
        raise HTTPException(status_code=500, detail="Graph query failed")

    agents = []
    for row in rows:
        a = row.get("agent", {})
        i = row.get("identity", {})
        tags = i.get("tags")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                pass

        agents.append({
            "agent_id": a.get("agent_id"),
            "workload_id": a.get("workload_id"),
            "host_id": a.get("host_id"),
            "nhi_id": i.get("nhi_id"),
            "verified": i.get("verified"),
            "account_id": i.get("account_id"),
            "tags": tags,
            "first_seen": i.get("first_seen"),
        })
    return agents


@router.get("/agents/{agent_id:path}/timeline")
def agent_timeline(agent_id: str):
    """Return the invocation timeline for a specific agent."""
    decoded = unquote(agent_id)

    agent_check = execute_cypher(
        f"MATCH (a:Agent {{agent_id: '{decoded}'}}) RETURN a"
    )
    if not agent_check:
        raise HTTPException(status_code=404, detail="Agent not found")

    query = f"""
        MATCH (a:Agent {{agent_id: '{decoded}'}})-[r:invokes]->(t:Tool)
        RETURN r, t
    """
    try:
        rows = execute_cypher_multi(query, ["edge", "tool"])
    except Exception:
        logger.exception("Failed to get timeline for agent %s", decoded)
        raise HTTPException(status_code=500, detail="Graph query failed")

    timeline = []
    for row in rows:
        e = row.get("edge", {})
        t = row.get("tool", {})
        timeline.append({
            "destination": t.get("destination"),
            "tool_type": t.get("tool_type"),
            "timestamp": e.get("timestamp"),
            "method": e.get("method"),
            "path": e.get("path"),
        })

    timeline.sort(key=lambda x: x.get("timestamp", ""))
    return timeline
