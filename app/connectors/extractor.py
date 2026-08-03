"""Small, dependency-free path resolver used to pull a list of records (and a
per-record id) out of an arbitrary JSON response.

We deliberately did not reach for a full JSONPath library: every real-world
response we needed to handle (a top-level array, or one named list field, or
a nested `data.items`) is expressible as a dotted path. If a future source
needs predicates or wildcards, this is the seam to swap in `jsonpath-ng`
without touching callers — extract_records()/extract_id() are the only two
functions the rest of the app depends on.
"""
import hashlib
import json
from typing import Any, Optional


def dotted_get(obj: Any, path: Optional[str], default: Any = None) -> Any:
    """Resolve a dotted path like 'data.items' against a JSON-like object.
    '$' or '' or None means "the object itself". List segments are treated
    as integer indexes."""
    if path in ("$", "", None):
        return obj
    current = obj
    for part in path.split("."):
        if current is None:
            return default
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return default
        else:
            return default
    return current


def extract_records(payload: Any, records_path: str) -> list:
    """Return the list of records found at records_path. A single object
    found there is wrapped in a list; anything missing yields []."""
    data = dotted_get(payload, records_path, default=[])
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return [data]


def extract_id(record: dict, id_field: Optional[str]) -> str:
    """Return a stable external id for a record. Prefers the configured
    id_field; falls back to a content hash so sources with no natural key
    still dedupe correctly on identical payloads (and get a new row when
    the content genuinely changes)."""
    if id_field:
        value = dotted_get(record, id_field)
        if value is not None:
            return str(value)
    canonical = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
