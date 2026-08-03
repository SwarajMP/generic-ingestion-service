"""Reference implementation showing how a second destination plugs in.
Not wired into the demo (no AWS credentials assumed in this environment),
but it satisfies the same Destination interface as PostgresDestination, so
the engine, connectors, and API layer need zero changes to use it --
only app/main.py's destination wiring would change (or fan out to both).
"""
import json
import logging
from typing import Any, Dict, Iterable, Optional

from app.connectors.extractor import extract_id
from app.destinations.base import Destination

logger = logging.getLogger(__name__)

try:
    import boto3
except ImportError:  # boto3 is not in requirements.txt; only needed if this is used
    boto3 = None


class S3Destination(Destination):
    def __init__(self, bucket: str, prefix: str = "", client=None):
        if client is None:
            if boto3 is None:
                raise RuntimeError("boto3 is required to use S3Destination (pip install boto3)")
            client = boto3.client("s3")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = client

    def save_batch(
        self,
        source_name: str,
        endpoint_name: str,
        records: Iterable[Dict[str, Any]],
        run_id: Any,
        id_field: Optional[str] = None,
    ) -> int:
        written = 0
        for record in records:
            external_id = extract_id(record, id_field)
            key_parts = [p for p in (self.prefix, source_name, endpoint_name, str(run_id), f"{external_id}.json") if p]
            key = "/".join(key_parts)
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json.dumps(record).encode("utf-8"),
                ContentType="application/json",
            )
            written += 1
        return written
