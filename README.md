# Agent Discovery Pipeline

Discover and visualize non-human AI agent identities by correlating runtime network events with cloud IAM inventory. Events flow through an OpenTelemetry Collector into a graph database (PostgreSQL + Apache AGE), and a React frontend renders the results.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Architecture Overview](#architecture-overview)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
5. [Project Structure](#project-structure)
6. [Data Flow (End-to-End)](#data-flow-end-to-end)
7. [Component Deep Dive](#component-deep-dive)
   - [Data Sources](#1-data-sources)
   - [OTel Collector](#2-otel-collector)
   - [Backend: OTLP Receiver](#3-backend-otlp-receiver)
   - [Backend: Graph Writer](#4-backend-graph-writer)
   - [Backend: Database Layer](#5-backend-database-layer-dbpy)
   - [Backend: Read API](#6-backend-read-api)
   - [Frontend](#7-frontend)
8. [Canonical Event Schema](#canonical-event-schema)
9. [Graph Database Schema](#graph-database-schema)
10. [Docker Compose Services](#docker-compose-services)
11. [Edge Case Handling](#edge-case-handling)
12. [Design Decisions & Trade-offs](#design-decisions--trade-offs)
13. [What Works](#what-works)


---

## Problem Statement

Modern infrastructure runs dozens of autonomous AI agents — LangChain chains, CrewAI crews, AutoGen workflows — each operating under cloud IAM roles. Security teams need answers to:

- **What AI agents exist** in our cloud accounts?
- **Which external services** is each agent calling (OpenAI, Anthropic, Bedrock, etc.)?
- **Which IAM identity** does each agent operate under?
- **Are all agent identities accounted for** in our inventory, or are there rogue unverified ones?

This pipeline answers those questions by correlating two data sources into a property graph.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Docker Compose Network                            │
│                                                                             │
│  ┌──────────────────┐     ┌──────────────────┐     ┌────────────────────┐  │
│  │  data/            │     │  OTel Collector   │     │  FastAPI Backend   │  │
│  │  runtime_events   │────▶│                   │────▶│                    │  │
│  │  .jsonl           │     │  filelog receiver  │     │  POST /v1/logs     │  │
│  │                   │     │  transform proc.  │     │  (OTLP receiver)   │  │
│  │  cloud_inventory  │────▶│  otlphttp export  │     │         │          │  │
│  │  .jsonl           │     │                   │     │         ▼          │  │
│  └──────────────────┘     └──────────────────┘     │  ┌──────────────┐  │  │
│                                                     │  │ Graph Writer  │  │  │
│                                                     │  └──────┬───────┘  │  │
│  ┌──────────────────┐                              │         │          │  │
│  │  React Frontend  │◀─────── GET /api/agents ─────│         ▼          │  │
│  │  (nginx:80)      │                              │  ┌──────────────┐  │  │
│  └──────────────────┘                              │  │ PostgreSQL   │  │  │
│                                                     │  │ + Apache AGE │  │  │
│                                                     │  └──────────────┘  │  │
│                                                     └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key insight**: The OTel Collector handles all parsing and normalization. The backend receives clean, structured OTLP log records and writes them into a graph. The frontend reads the graph via a REST API.

---

## Prerequisites

- Docker and Docker Compose v2+
- ~2 GB free disk space (for container images)
- Ports 3000, 5432, 8000 available

---

## Quick Start

```bash
# Clone and enter the project
cd mvp-platform

# Start all services (db, backend, frontend)
docker compose up -d --build

# Replay JSONL data through the OTel Collector
docker compose run --rm otel-collector

# Open the UI
open http://localhost:3000
```

To verify idempotency, run the collector again — no duplicate nodes or edges will be created.

To tear down:
```bash
docker compose down -v
```

---

## Project Structure

```
mvp-platform/
├── docker-compose.yml              # Orchestrates all 4 services
├── README.md                       # This file
├── data/
│   ├── runtime_events.jsonl        # Simulated agent network traffic
│   └── cloud_inventory.jsonl       # Simulated IAM role inventory
├── otel/
│   └── otel-collector-config.yaml  # Collector pipeline config
├── backend/
│   ├── Dockerfile                  # Python 3.12 slim image
│   ├── requirements.txt            # FastAPI, psycopg2, pydantic, uvicorn
│   ├── ingest/
│   │   ├── __init__.py
│   │   └── schema.py              # CanonicalEvent Pydantic model
│   └── app/
│       ├── __init__.py
│       ├── main.py                # FastAPI app entry point + startup
│       ├── db.py                  # Connection pool + AGE helpers
│       ├── otlp_receiver.py       # POST /v1/logs endpoint
│       ├── graph_writer.py        # Cypher upsert logic
│       └── routes.py              # GET /api/agents, GET /api/agents/{id}/timeline
└── frontend/
    ├── Dockerfile                  # Multi-stage: Node build + nginx serve
    ├── nginx.conf                  # Reverse proxy /api → backend
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── postcss.config.js
    ├── index.html
    └── src/
        ├── main.tsx               # React entry point
        ├── App.tsx                # Router setup
        ├── api.ts                 # HTTP client functions
        ├── index.css              # Tailwind imports
        ├── vite-env.d.ts
        └── components/
            ├── AgentList.tsx       # Table view of all agents
            └── AgentDetail.tsx     # Agent info + invocation timeline
```

---

## Data Flow (End-to-End)

Here's exactly what happens when you run `docker compose run --rm otel-collector`:

```
1. Collector reads runtime_events.jsonl line by line
2. json_parser operator parses each JSON line into log attributes
3. transform/runtime processor:
   - Adds attributes["source"] = "runtime"
   - Renames sni → tool_destination, ts → timestamp
   - Computes agent_id = Concat(nhi_id, "::", workload_id)
4. otlphttp exporter sends logs as JSON to POST http://backend:8000/v1/logs

5. Backend receives the gzip-compressed (or plain) JSON payload
6. otlp_receiver.py:
   - Decompresses if gzip
   - Parses OTLP envelope: resourceLogs → scopeLogs → logRecords
   - Flattens each logRecord's attributes array into a dict
   - Validates against CanonicalEvent schema
   - Dispatches to graph_writer based on source field

7. graph_writer.py:
   - Opens a PostgreSQL connection with AGE loaded
   - Executes a sequence of MERGE Cypher statements:
     • MERGE Identity node (by nhi_id)
     • MERGE Agent node (by agent_id)
     • MERGE Tool node (by destination)
     • MERGE owns edge (Identity → Agent)
     • MERGE invokes edge (Agent → Tool)
   - Commits the transaction

8. Same flow for cloud_inventory.jsonl, but:
   - transform/inventory normalizes iam_role_arn → nhi_id
   - graph_writer only creates/updates an Identity node with verified=true

9. Frontend fetches GET /api/agents → Cypher MATCH traverses the graph
10. User sees agents with verified/unverified status and tool timelines
```

---

## Component Deep Dive

### 1. Data Sources

**`data/runtime_events.jsonl`** — Each line represents an observed network call from an AI agent:
```json
{
  "nhi_id": "arn:aws:iam::111:role/agent-role-a",
  "workload_id": "wl-langchain-1",
  "host_id": "i-abc123",
  "sni": "api.openai.com",
  "method": "POST",
  "path": "/v1/chat/completions",
  "ts": "2024-11-01T10:00:00Z"
}
```

Fields: `nhi_id` (IAM role ARN the agent uses), `workload_id` (unique workload identifier), `host_id` (EC2 instance), `sni` (TLS SNI = destination hostname), `method`/`path` (HTTP details), `ts` (timestamp).

**`data/cloud_inventory.jsonl`** — Each line represents a known IAM role from cloud inventory:
```json
{
  "iam_role_arn": "arn:aws:iam::111:role/agent-role-a",
  "account_id": "111",
  "first_seen": "2024-10-15T00:00:00Z",
  "snapshot_ts": "2024-11-01T09:00:00Z",
  "tags": {"team": "ml-platform", "env": "prod", "purpose": "langchain-agent"}
}
```

The correlation key between the two sources is **`nhi_id` = `iam_role_arn`**.

---

### 2. OTel Collector

**File**: `otel/otel-collector-config.yaml`

The collector uses the **OpenTelemetry Collector Contrib** distribution which includes the `filelog` receiver and `transform` processor.

**Receivers** — Two `filelog` receivers, one per source file. Each uses `json_parser` with `parse_to: attributes` to place all parsed JSON fields directly into log record attributes (not body, which would remain a string type and break downstream indexing).

**Processors** — Two `transform` processors apply OTTL (OpenTelemetry Transformation Language) statements:

- `transform/runtime`: Sets a `source` tag, renames `sni` → `tool_destination` and `ts` → `timestamp`, and computes `agent_id` via `Concat([nhi_id, workload_id], "::")`.
- `transform/inventory`: Sets a `source` tag, renames `iam_role_arn` → `nhi_id` and `snapshot_ts` → `timestamp`.

**Exporter** — Single `otlphttp` exporter with `encoding: json` (critical: the default is protobuf, which the backend doesn't decode). TLS is disabled since communication is internal to the Docker network.

**Pipelines** — Two separate log pipelines ensure each source goes through its own transform processor:
```
logs/runtime:   filelog/runtime  → transform/runtime  → otlphttp
logs/inventory: filelog/inventory → transform/inventory → otlphttp
```

---

### 3. Backend: OTLP Receiver

**File**: `backend/app/otlp_receiver.py`

This implements the write path — receiving OTLP log data from the collector.

**Gzip handling**: The collector may send gzip-compressed payloads. The receiver checks for the gzip magic bytes (`\x1f\x8b`) or the `content-encoding: gzip` header and decompresses before parsing.

**OTLP envelope parsing**: OTLP JSON wraps log records in a nested structure:
```
resourceLogs[] → scopeLogs[] → logRecords[] → attributes[]
```
Each attribute is `{"key": "...", "value": {"stringValue": "..."}}`. The `_extract_attributes` function flattens this into a simple `{"key": "value"}` dict, handling all OTLP value types (string, bool, int, double, kvlist, array).

**Validation**: The flattened attributes are passed to `_attrs_to_event()` which constructs a `CanonicalEvent` Pydantic model. Records missing `source` or `nhi_id` are skipped with a warning.

**Dispatch**: Based on `event.source`, the receiver calls either `graph_writer.upsert_runtime_event()` or `graph_writer.upsert_inventory_event()`.

---

### 4. Backend: Graph Writer

**File**: `backend/app/graph_writer.py`

This is the core graph logic — translating canonical events into graph mutations.

**`upsert_runtime_event(event)`** executes 5-6 Cypher statements per event:

1. **MERGE Identity** — Creates the Identity node if it doesn't exist (keyed by `nhi_id`).
2. **Conditional SET verified** — Only sets `verified=false` if the property is NULL (preserves `verified=true` set by inventory).
3. **MERGE Agent** — Creates or updates the Agent node (keyed by `agent_id`), always setting `workload_id` and `host_id`.
4. **MERGE Tool** — Creates the Tool node (keyed by `destination`), sets `tool_type` derived from the hostname (openai/anthropic/bedrock/other).
5. **MERGE owns edge** — Links Identity → Agent (idempotent, no duplicates).
6. **MERGE invokes edge** — Links Agent → Tool with `timestamp` and `destination` in the match key (deduplicates identical calls). Sets `method` and `path` as properties.

**`upsert_inventory_event(event)`** executes 1 Cypher statement:

1. **MERGE Identity + SET verified=true** — Creates or updates the Identity node, always marking it as verified and setting `account_id`, `tags`, and `first_seen`.

**Tool classification** (`_classify_tool`): Inspects the destination hostname to categorize tools — this powers the color-coded badges in the frontend.

**String escaping** (`_escape`): Since Apache AGE doesn't support parameterized Cypher queries, all string values are escaped to prevent Cypher injection within the internal tool.

---

### 5. Backend: Database Layer (db.py)

**File**: `backend/app/db.py`

**Connection pool**: Uses `psycopg2.pool.SimpleConnectionPool` (1-10 connections). Connections are checked out with `get_conn()` and returned with `put_conn()`.

**Graph initialization** (`init_graph`): Called at FastAPI startup. Creates the AGE extension, loads it, and creates the `agent_discovery` graph if it doesn't exist. Checks `ag_catalog.ag_graph` to avoid duplicate creation errors.

**AGE result parsing**: AGE returns query results as text representations like:
```
{"id": 123, "label": "Agent", "properties": {"agent_id": "..."}}::vertex
```
The `_parse_age_value` function uses regex to extract the `properties` JSON from these vertex/edge strings.

**Query helpers**:
- `execute_cypher(query)` — For single-column returns. Parses each row into a properties dict.
- `execute_cypher_multi(query, columns)` — For multi-column returns (e.g., `RETURN a, i`). Each column is parsed separately and assembled into a named dict.

Both helpers handle the AGE boilerplate: `LOAD 'age'`, set `search_path`, and wrap the Cypher in `SELECT * FROM cypher('graph_name', $$ ... $$)`.

---

### 6. Backend: Read API

**File**: `backend/app/routes.py`

**`GET /api/agents`** — Traverses the graph to find all agents with their owning identity:
```cypher
MATCH (i:Identity)-[:owns]->(a:Agent)
RETURN a, i
```
Returns a JSON array with agent + identity properties merged. Tags are deserialized from their stored JSON string.

**`GET /api/agents/{agent_id}/timeline`** — For a specific agent, finds all outbound tool calls:
```cypher
MATCH (a:Agent {agent_id: '...'})-[r:invokes]->(t:Tool)
RETURN r, t
```
Returns timeline entries sorted by timestamp, each with destination, tool_type, method, and path.

The `{agent_id:path}` route parameter allows the agent ID (which contains `/` and `::` characters) to be passed in the URL path.

---

### 7. Frontend

**Stack**: React 18 + TypeScript + Vite + Tailwind CSS + React Router v6

**`App.tsx`** — Sets up the router with two routes and a sticky header with the "AD" logo.

**`AgentList.tsx`** — The home page. Fetches `/api/agents` on mount and renders a table with columns: Workload (clickable link), Host, Identity (NHI ARN), and Status (verified/unverified badge). Handles loading, error, and empty states.

**`AgentDetail.tsx`** — The detail page. Fetches both the agent list (to find the specific agent's metadata) and the timeline endpoint. Renders:
- An info card with agent properties (ID, host, NHI, account, first_seen, tags)
- A vertical timeline of tool invocations, each with a color-coded badge (green=OpenAI, orange=Anthropic, blue=Bedrock, gray=other), the destination hostname, and the HTTP method/path.

**`api.ts`** — Typed fetch functions (`fetchAgents`, `fetchTimeline`) that hit the backend. In Docker, nginx proxies `/api` requests to the backend.

**`nginx.conf`** — Serves the Vite build output as static files, proxies `/api/` to `http://backend:8000`, and falls back to `index.html` for client-side routing.

---

## Canonical Event Schema

Defined in `backend/ingest/schema.py` — the single source of truth shared between the OTel transform rules and the backend.

| Field              | Type                       | Set By    | Description                                    |
|--------------------|----------------------------|-----------|------------------------------------------------|
| `agent_id`         | `str \| None`              | runtime   | `"{nhi_id}::{workload_id}"` — stable agent key |
| `nhi_id`           | `str` (required)           | both      | IAM role ARN — the identity key                |
| `workload_id`      | `str \| None`              | runtime   | Logical workload name (e.g. `wl-langchain-1`)  |
| `host_id`          | `str \| None`              | runtime   | EC2 instance ID where the agent runs           |
| `tool_destination` | `str \| None`              | runtime   | SNI hostname being called (e.g. `api.openai.com`) |
| `timestamp`        | `str` (required)           | both      | ISO-8601 UTC timestamp of the event            |
| `source`           | `"runtime" \| "inventory"` | both      | Which pipeline produced this event             |
| `method`           | `str \| None`              | runtime   | HTTP method (POST, GET, etc.)                  |
| `path`             | `str \| None`              | runtime   | HTTP path called                               |
| `tags`             | `dict \| None`             | inventory | IAM tags from cloud inventory                  |
| `account_id`       | `str \| None`              | inventory | AWS account ID                                 |
| `first_seen`       | `str \| None`              | inventory | When the IAM role was first observed           |

---

## Graph Database Schema

The graph is stored in PostgreSQL using the **Apache AGE** extension, which adds Cypher query support to Postgres.

### Node Types

```
┌─────────────────────┐     owns      ┌─────────────────────┐    invokes    ┌─────────────────┐
│      Identity       │──────────────▶│        Agent        │─────────────▶│      Tool       │
│                     │               │                     │              │                 │
│ nhi_id (PK)        │               │ agent_id (PK)       │              │ destination (PK)│
│ verified: bool      │               │ workload_id: str    │              │ tool_type: str  │
│ account_id: str     │               │ host_id: str        │              │                 │
│ tags: str (JSON)    │               │                     │              │                 │
│ first_seen: str     │               │                     │              │                 │
└─────────────────────┘               └─────────────────────┘              └─────────────────┘
```

- **Identity** — Represents an IAM role (non-human identity). `verified=true` means a matching cloud inventory record exists.
- **Agent** — Represents a discovered AI workload. Keyed by `agent_id = "{nhi_id}::{workload_id}"`.
- **Tool** — Represents an external service. `tool_type` is derived from the hostname (openai, anthropic, bedrock, other).

### Edge Types

- **owns** (Identity → Agent) — "This IAM role is the identity under which this agent runs." One identity can own many agents.
- **invokes** (Agent → Tool) — "This agent made an outbound call to this tool." Properties: `timestamp`, `destination`, `method`, `path`. Deduped by `(agent_id, destination, timestamp)`.

### Why MERGE?

All writes use Cypher `MERGE` (match-or-create). This means:
- First run: creates all nodes and edges
- Second run: matches existing nodes/edges, updates properties
- Net result: **zero duplicates regardless of how many times you replay**

---

## Docker Compose Services

| Service            | Image                                    | Port  | Role                                                       |
|--------------------|------------------------------------------|-------|------------------------------------------------------------|
| **db**             | `apache/age:release_PG16_1.5.0`          | 5432  | PostgreSQL 16 + AGE graph extension                        |
| **backend**        | Custom (Python 3.12 slim)                | 8000  | FastAPI: OTLP receiver + REST API                          |
| **otel-collector** | `otel/opentelemetry-collector-contrib:0.97.0` | —  | Reads JSONL, normalizes, exports OTLP to backend           |
| **frontend**       | Custom (Node 20 build + nginx alpine)    | 3000  | Serves React app, proxies API calls to backend             |

**Dependency chain**: `db` (healthcheck) → `backend` (depends_on db healthy) → `otel-collector` (depends_on backend) + `frontend` (depends_on backend)

---

## Edge Case Handling

### Duplicate Events (Idempotent Replay)

Every write uses `MERGE` with a unique key:
- Identity: `nhi_id`
- Agent: `agent_id`
- Tool: `destination`
- invokes edge: `(agent_id, destination, timestamp)`

Replaying the collector produces no new nodes or edges. Properties are updated (SET) to the same values.

### Out-of-Order Events

Runtime events create `Identity(verified=NULL → false)`. If a matching inventory record has already been processed, `verified` is already `true` and the conditional `WHERE i.verified IS NULL` prevents overwriting. If inventory arrives later, it unconditionally sets `verified=true`.

### Missing Inventory Match

If a runtime event references an `nhi_id` with no corresponding inventory record:
- The Identity node is created with `verified=false`
- The agent and its tool calls are fully recorded
- The UI shows an "Unverified" amber badge
- No errors — the pipeline continues gracefully

### Gzip and Encoding

The OTel Collector may compress payloads. The OTLP receiver detects gzip by checking the first two bytes for the magic number `\x1f\x8b`, or the `content-encoding: gzip` header. The exporter is configured with `encoding: json` to avoid protobuf (which would require protobuf deserialization libraries).

---

## Design Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| OTel Collector for ingestion | Standard observability tooling; field-proven file tailing; OTTL for transformation without custom code |
| Apache AGE over Neo4j | Runs as a Postgres extension (single database), no separate license, Cypher-compatible |
| MERGE without ON CREATE/ON MATCH | AGE doesn't support these clauses; we use conditional MATCH + SET as a workaround |
| String interpolation in Cypher | AGE's parameterized query support is limited; acceptable for an internal discovery tool |
| `encoding: json` on otlphttp | Avoids needing protobuf deserialization in Python; simpler receiver implementation |
| `parse_to: attributes` in json_parser | Prevents the "body of type Str cannot be indexed" error in transform processors |
| Monolithic backend | Single FastAPI process handles both write (OTLP) and read (API) paths for simplicity |
| No authentication | Internal tool / MVP scope; would add OAuth2 middleware for production |

---

## What Works

- Full pipeline: JSONL → OTel Collector → OTLP receiver → graph upsert → REST API → React UI
- Idempotent replay (run collector multiple times safely)
- Runtime + inventory correlation via shared `nhi_id`
- Verified/unverified identity status badge
- Tool classification by hostname (OpenAI, Anthropic, Bedrock, other)
- Timeline view of all tool invocations per agent
- Docker Compose one-command setup

---