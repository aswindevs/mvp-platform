from __future__ import annotations

import json
import logging

from ingest.schema import CanonicalEvent

from .db import GRAPH_NAME, get_conn, put_conn

logger = logging.getLogger(__name__)


def _classify_tool(destination: str) -> str:
    """Derive a tool_type from the SNI hostname."""
    d = destination.lower()
    if "anthropic" in d:
        return "anthropic"
    if "openai" in d:
        return "openai"
    if "bedrock" in d:
        return "bedrock"
    return "other"


def _escape(value: str | None) -> str:
    """Escape a string for embedding in a Cypher literal."""
    if value is None:
        return ""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _run_cypher(conn, cur, query: str):
    """Execute a single Cypher statement inside an existing cursor/connection."""
    sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $$ {query} $$) as (v agtype);"
    cur.execute(sql)


def upsert_runtime_event(event: CanonicalEvent):
    """Process a runtime event: upsert Identity, Agent, Tool nodes + edges."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')

            nhi = _escape(event.nhi_id)
            agent_id = _escape(event.agent_id)
            wl = _escape(event.workload_id)
            host = _escape(event.host_id)
            dest = _escape(event.tool_destination)
            tool_type = _classify_tool(event.tool_destination or "")
            ts = _escape(event.timestamp)
            method = _escape(event.method)
            path = _escape(event.path)

            _run_cypher(conn, cur, f"""
                MERGE (i:Identity {{nhi_id: '{nhi}'}})
                RETURN i
            """)

            _run_cypher(conn, cur, f"""
                MATCH (i:Identity {{nhi_id: '{nhi}'}})
                WHERE i.verified IS NULL
                SET i.verified = false
                RETURN i
            """)

            _run_cypher(conn, cur, f"""
                MERGE (a:Agent {{agent_id: '{agent_id}'}})
                SET a.workload_id = '{wl}', a.host_id = '{host}'
                RETURN a
            """)

            if dest:
                _run_cypher(conn, cur, f"""
                    MERGE (t:Tool {{destination: '{dest}'}})
                    SET t.tool_type = '{tool_type}'
                    RETURN t
                """)

            _run_cypher(conn, cur, f"""
                MATCH (i:Identity {{nhi_id: '{nhi}'}}), (a:Agent {{agent_id: '{agent_id}'}})
                MERGE (i)-[:owns]->(a)
                RETURN i
            """)

            if dest:
                _run_cypher(conn, cur, f"""
                    MATCH (a:Agent {{agent_id: '{agent_id}'}}), (t:Tool {{destination: '{dest}'}})
                    MERGE (a)-[r:invokes {{timestamp: '{ts}', destination: '{dest}'}}]->(t)
                    SET r.method = '{method}', r.path = '{path}'
                    RETURN r
                """)

            conn.commit()
            logger.debug("Upserted runtime event for agent %s", event.agent_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


def upsert_inventory_event(event: CanonicalEvent):
    """Process an inventory event: upsert Identity node with verified=true."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')

            nhi = _escape(event.nhi_id)
            acct = _escape(event.account_id)
            first_seen = _escape(event.first_seen)
            tags_str = _escape(json.dumps(event.tags)) if event.tags else ""

            _run_cypher(conn, cur, f"""
                MERGE (i:Identity {{nhi_id: '{nhi}'}})
                SET i.verified = true, i.account_id = '{acct}',
                    i.tags = '{tags_str}', i.first_seen = '{first_seen}'
                RETURN i
            """)

            conn.commit()
            logger.debug("Upserted inventory event for identity %s", event.nhi_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
