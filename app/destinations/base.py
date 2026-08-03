from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Optional


class Destination(ABC):
    """Anything that can durably store a batch of raw records. The
    ingestion engine only ever talks to this interface, so swapping Postgres
    for S3 (or writing to both) never touches the connector/pagination code.
    """

    @abstractmethod
    def save_batch(
        self,
        source_name: str,
        endpoint_name: str,
        records: Iterable[Dict[str, Any]],
        run_id: Any,
        id_field: Optional[str] = None,
    ) -> int:
        """Persist a batch of records; return the number written."""
        ...
