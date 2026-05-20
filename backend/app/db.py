from __future__ import annotations

import json
import logging
import os
import re

import psycopg2
from psycopg2 import pool

logger = logging.getLogger(__name__)

GRAPH_NAME = "agent_discovery"

_pool: pool.SimpleConnectionPool | None = None


def get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=os.getenv("PG_HOST", "localhost"),
            port=int(os.getenv("PG_PORT", "5432")),
            user=os.getenv("PG_USER", "graph"),
            password=os.getenv("PG_PASSWORD", "graph"),
            dbname=os.getenv("PG_DB", "agent_discovery"),
        )
    return _pool


def get_conn():
    return get_pool().getconn()


def put_conn(conn):
    get_pool().putconn(conn)


def init_graph():
    """Create the AGE extension and the graph if they don't already exist."""
    conn = get_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS age;")
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')
            cur.execute(
                "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = %s",
                (GRAPH_NAME,),
            )
            if cur.fetchone()[0] == 0:
                cur.execute("SELECT create_graph(%s);", (GRAPH_NAME,))
                logger.info("Created graph %s", GRAPH_NAME)
            else:
                logger.info("Graph %s already exists", GRAPH_NAME)
    finally:
        conn.autocommit = False
        put_conn(conn)


_AGE_VERTEX_RE = re.compile(
    r'\{"id":\s*\d+,\s*"label":\s*"[^"]*",\s*"properties":\s*(\{.*?\})\}::vertex'
)
_AGE_EDGE_RE = re.compile(
    r'\{"id":\s*\d+,\s*"label":\s*"[^"]*",\s*"end_id":\s*\d+,\s*"start_id":\s*\d+,\s*"properties":\s*(\{.*?\})\}::edge'
)


def _parse_age_value(raw: str) -> dict | None:
    """Extract properties dict from an AGE vertex/edge text representation."""
    for pattern in (_AGE_VERTEX_RE, _AGE_EDGE_RE):
        m = pattern.search(raw)
        if m:
            return json.loads(m.group(1))
    return None


def execute_cypher(query: str, params: dict | None = None) -> list[dict]:
    """Run a Cypher query against the agent_discovery graph via ag_catalog.

    Returns a list of dicts — one per row — where each column that looks like
    an AGE vertex/edge is parsed into its properties dict.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')

            if params:
                cypher_params = ", ".join(
                    f"'{json.dumps(v)}'" if isinstance(v, (dict, list)) else
                    f"'{v}'" if isinstance(v, str) else
                    str(v)
                    for v in params.values()
                )
                sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $$ {query} $$, '{{{cypher_params}}}') as (result agtype);"
            else:
                sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $$ {query} $$) as (result agtype);"

            cur.execute(sql)
            rows = cur.fetchall()
            conn.commit()

            results = []
            for row in rows:
                if row[0] is None:
                    continue
                raw = str(row[0])
                parsed = _parse_age_value(raw)
                if parsed is not None:
                    results.append(parsed)
                else:
                    results.append({"_raw": raw})
            return results
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


def execute_cypher_multi(query: str, columns: list[str]) -> list[dict]:
    """Run a Cypher query returning multiple columns.

    `columns` names each positional column; each is parsed as an AGE
    vertex/edge and assembled into a single dict per row.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')

            col_defs = ", ".join(f"{c} agtype" for c in columns)
            sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $$ {query} $$) as ({col_defs});"

            cur.execute(sql)
            rows = cur.fetchall()
            conn.commit()

            results = []
            for row in rows:
                record = {}
                for idx, col_name in enumerate(columns):
                    raw = str(row[idx]) if row[idx] is not None else None
                    if raw:
                        parsed = _parse_age_value(raw)
                        if parsed:
                            record[col_name] = parsed
                        else:
                            record[col_name] = raw
                results.append(record)
            return results
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
