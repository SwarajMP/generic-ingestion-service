import logging
import uuid
from datetime import datetime, timezone

from app.connectors.client import GenericApiConnector
from app.destinations.base import Destination
from app.models import IngestionRun
from app.schemas import EndpointConfig, SourceConfig

logger = logging.getLogger(__name__)


class IngestionEngine:
    """Orchestrates one (source, endpoint) pull: opens a connector, streams
    pages to the destination, and records what happened as an IngestionRun.
    Takes the session_factory as a dependency so tests can point it at a
    throwaway database instead of whatever DATABASE_URL is configured."""

    def __init__(self, destination: Destination, session_factory):
        self.destination = destination
        self.session_factory = session_factory

    def run(self, source: SourceConfig, endpoint: EndpointConfig) -> IngestionRun:
        session = self.session_factory()
        run = IngestionRun(
            id=uuid.uuid4(),
            source_name=source.name,
            endpoint_name=endpoint.name,
            status="running",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

        connector = GenericApiConnector(source, endpoint)
        pages = 0
        total_records = 0
        try:
            for page_index, records in connector.fetch_all():
                pages += 1
                written = self.destination.save_batch(
                    source.name, endpoint.name, records, run_id, id_field=endpoint.id_field
                )
                total_records += written
                logger.info(
                    "source=%s endpoint=%s page=%s fetched=%s written=%s",
                    source.name, endpoint.name, page_index, len(records), written,
                )
            run.status = "success"
        except Exception as exc:
            logger.exception("Ingestion failed for %s/%s", source.name, endpoint.name)
            run.status = "failed"
            run.error_message = str(exc)[:2000]
        finally:
            run.pages_fetched = pages
            run.records_ingested = total_records
            run.finished_at = datetime.now(timezone.utc)
            session.add(run)
            session.commit()
            session.refresh(run)
            connector.close()
            session.close()
        return run
