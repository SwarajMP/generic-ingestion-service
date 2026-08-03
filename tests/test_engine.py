"""Engine orchestration tests. Uses a FakeDestination (itself proof the
Destination interface is a real seam, not just PostgresDestination with
extra steps) and a FakeSession so these run with no real database --
the real Postgres path is exercised end-to-end via docker-compose (see
README's manual-demo section)."""
import httpx
import respx

from app.ingestion.engine import IngestionEngine
from app.schemas import AuthConfig, EndpointConfig, PaginationConfig, RetryConfig, SourceConfig


class FakeDestination:
    def __init__(self):
        self.saved = []

    def save_batch(self, source_name, endpoint_name, records, run_id, id_field=None):
        records = list(records)
        self.saved.extend(records)
        return len(records)


class FakeSession:
    def add(self, obj):
        pass

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def close(self):
        pass


def fake_session_factory():
    return FakeSession()


@respx.mock
def test_engine_runs_successfully_and_records_stats():
    respx.get("https://fake.test/items").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 1}, {"id": 2}], "next": None})
    )
    source = SourceConfig(name="fake", base_url="https://fake.test", auth=AuthConfig(type="none"), endpoints=[])
    endpoint = EndpointConfig(
        name="items",
        path="/items",
        records_path="results",
        id_field="id",
        pagination=PaginationConfig(type="next_url", next_field="next"),
    )
    destination = FakeDestination()
    engine = IngestionEngine(destination, fake_session_factory)

    run = engine.run(source, endpoint)

    assert run.status == "success"
    assert run.pages_fetched == 1
    assert run.records_ingested == 2
    assert destination.saved == [{"id": 1}, {"id": 2}]


@respx.mock
def test_engine_marks_run_failed_on_persistent_error():
    respx.get("https://fake.test/items").mock(return_value=httpx.Response(500))
    source = SourceConfig(
        name="fake",
        base_url="https://fake.test",
        auth=AuthConfig(type="none"),
        retry=RetryConfig(max_attempts=1),
        endpoints=[],
    )
    endpoint = EndpointConfig(name="items", path="/items", records_path="results", pagination=PaginationConfig(type="none"))
    destination = FakeDestination()
    engine = IngestionEngine(destination, fake_session_factory)

    run = engine.run(source, endpoint)

    assert run.status == "failed"
    assert run.error_message
    assert run.records_ingested == 0
    assert destination.saved == []


@respx.mock
def test_engine_streams_multiple_pages_to_destination():
    respx.get("https://fake.test/items", params={}).mock(
        return_value=httpx.Response(200, json={"results": [{"id": 1}], "next": "https://fake.test/items2"})
    )
    respx.get("https://fake.test/items2").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 2}], "next": None})
    )
    source = SourceConfig(name="fake", base_url="https://fake.test", auth=AuthConfig(type="none"), endpoints=[])
    endpoint = EndpointConfig(
        name="items",
        path="/items",
        records_path="results",
        id_field="id",
        pagination=PaginationConfig(type="next_url", next_field="next", max_pages=5),
    )
    destination = FakeDestination()
    engine = IngestionEngine(destination, fake_session_factory)

    run = engine.run(source, endpoint)

    assert run.pages_fetched == 2
    assert run.records_ingested == 2
    assert destination.saved == [{"id": 1}, {"id": 2}]
