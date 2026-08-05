import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.destinations.postgres_destination import PostgresDestination
from app.ingestion.engine import IngestionEngine
from app.models import IngestionRun
from app.sources.loader import load_sources

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

sources = {}
destination = PostgresDestination(SessionLocal)
ingestion_engine = IngestionEngine(destination, SessionLocal)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    global sources
    sources = load_sources(settings.sources_config_dir)
    logger.info("Loaded %d source(s): %s", len(sources), list(sources.keys()))
    yield


app = FastAPI(title="Generic Data Ingestion Service", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sources")
def list_sources():
    return [
        {
            "name": s.name,
            "base_url": s.base_url,
            "auth_type": s.auth.type,
            "endpoints": [
                {"name": e.name, "path": e.path, "pagination": e.pagination.type}
                for e in s.endpoints
            ],
        }
        for s in sources.values()
    ]


@app.post("/ingest/{source_name}/{endpoint_name}")
def trigger_ingestion(source_name: str, endpoint_name: str):
    source = sources.get(source_name)
    if not source:
        raise HTTPException(404, f"Unknown source '{source_name}'. Known sources: {list(sources.keys())}")
    endpoint = next((e for e in source.endpoints if e.name == endpoint_name), None)
    if not endpoint:
        known = [e.name for e in source.endpoints]
        raise HTTPException(404, f"Unknown endpoint '{endpoint_name}' for source '{source_name}'. Known: {known}")

    run = ingestion_engine.run(source, endpoint)
    return _run_to_dict(run)


@app.get("/runs")
def list_runs(limit: int = 20):
    session = SessionLocal()
    try:
        runs = (
            session.query(IngestionRun)
            .order_by(IngestionRun.started_at.desc())
            .limit(limit)
            .all()
        )
        return [_run_to_dict(r) for r in runs]
    finally:
        session.close()


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    session = SessionLocal()
    try:
        run = session.get(IngestionRun, run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return _run_to_dict(run)
    finally:
        session.close()


def _run_to_dict(run: IngestionRun) -> dict:
    return {
        "run_id": str(run.id),
        "source": run.source_name,
        "endpoint": run.endpoint_name,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "pages_fetched": run.pages_fetched,
        "records_ingested": run.records_ingested,
        "error": run.error_message,
    }
