from typing import Any, Dict, Iterable, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.connectors.extractor import extract_id
from app.destinations.base import Destination
from app.models import RawRecord


class PostgresDestination(Destination):
    """Upserts each record into raw_records keyed on
    (source_name, endpoint_name, external_id), so re-running an ingestion
    updates existing rows instead of duplicating them."""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save_batch(
        self,
        source_name: str,
        endpoint_name: str,
        records: Iterable[Dict[str, Any]],
        run_id: Any,
        id_field: Optional[str] = None,
    ) -> int:
        records = list(records)
        if not records:
            return 0
        session = self.session_factory()
        try:
            written = 0
            for record in records:
                external_id = extract_id(record, id_field)
                stmt = pg_insert(RawRecord).values(
                    source_name=source_name,
                    endpoint_name=endpoint_name,
                    external_id=external_id,
                    payload=record,
                    run_id=run_id,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["source_name", "endpoint_name", "external_id"],
                    set_={"payload": stmt.excluded.payload, "run_id": stmt.excluded.run_id},
                )
                session.execute(stmt)
                written += 1
            session.commit()
            return written
        finally:
            session.close()
