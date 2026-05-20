from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CanonicalEvent(BaseModel):
    """Single source-of-truth schema for all ingested events.

    Runtime events populate agent_id, workload_id, host_id, tool_destination,
    method, and path.  Inventory events populate account_id, tags, and
    first_seen.  Both sources always set nhi_id, timestamp, and source.
    """

    agent_id: str | None = None
    nhi_id: str
    workload_id: str | None = None
    host_id: str | None = None
    tool_destination: str | None = None
    timestamp: str
    source: Literal["runtime", "inventory"]
    method: str | None = None
    path: str | None = None
    tags: dict | None = None
    account_id: str | None = None
    first_seen: str | None = None
