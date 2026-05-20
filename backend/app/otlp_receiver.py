from __future__ import annotations

import gzip
import json
import logging

from fastapi import APIRouter, Request, Response

from ingest.schema import CanonicalEvent

from . import graph_writer

logger = logging.getLogger(__name__)
router = APIRouter()


def _extract_attributes(log_record: dict) -> dict:
    """Flatten OTLP attribute list into a simple dict."""
    attrs: dict = {}
    for attr in log_record.get("attributes", []):
        key = attr.get("key", "")
        value_obj = attr.get("value", {})
        if "stringValue" in value_obj:
            attrs[key] = value_obj["stringValue"]
        elif "boolValue" in value_obj:
            attrs[key] = value_obj["boolValue"]
        elif "intValue" in value_obj:
            attrs[key] = int(value_obj["intValue"])
        elif "doubleValue" in value_obj:
            attrs[key] = float(value_obj["doubleValue"])
        elif "kvlistValue" in value_obj:
            kv_pairs = value_obj["kvlistValue"].get("values", [])
            attrs[key] = {
                kv["key"]: kv.get("value", {}).get("stringValue", "")
                for kv in kv_pairs
            }
        elif "arrayValue" in value_obj:
            attrs[key] = json.dumps(value_obj["arrayValue"])
        else:
            attrs[key] = str(value_obj)
    return attrs


def _attrs_to_event(attrs: dict) -> CanonicalEvent | None:
    """Build a CanonicalEvent from flattened OTLP attributes, or None on error."""
    source = attrs.get("source")
    nhi_id = attrs.get("nhi_id")
    if not source or not nhi_id:
        logger.warning("Skipping log record: missing source or nhi_id")
        return None

    tags = attrs.get("tags")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            pass

    return CanonicalEvent(
        agent_id=attrs.get("agent_id"),
        nhi_id=nhi_id,
        workload_id=attrs.get("workload_id"),
        host_id=attrs.get("host_id"),
        tool_destination=attrs.get("tool_destination"),
        timestamp=attrs.get("timestamp", ""),
        source=source,
        method=attrs.get("method"),
        path=attrs.get("path"),
        tags=tags if isinstance(tags, dict) else None,
        account_id=attrs.get("account_id"),
        first_seen=attrs.get("first_seen"),
    )


@router.post("/v1/logs")
async def receive_otlp_logs(request: Request):
    """Accept OTLP/HTTP JSON log exports from the OTel Collector."""
    raw = await request.body()
    if request.headers.get("content-encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    body = json.loads(raw)
    processed = 0
    errors = 0

    for resource_log in body.get("resourceLogs", []):
        for scope_log in resource_log.get("scopeLogs", []):
            for log_record in scope_log.get("logRecords", []):
                attrs = _extract_attributes(log_record)
                event = _attrs_to_event(attrs)
                if event is None:
                    errors += 1
                    continue

                try:
                    if event.source == "runtime":
                        graph_writer.upsert_runtime_event(event)
                    elif event.source == "inventory":
                        graph_writer.upsert_inventory_event(event)
                    processed += 1
                except Exception:
                    logger.exception("Failed to upsert event: %s", event)
                    errors += 1

    logger.info("OTLP batch: processed=%d errors=%d", processed, errors)
    return Response(status_code=200)
