import httpx
import respx

from app.connectors.client import GenericApiConnector
from app.schemas import AuthConfig, EndpointConfig, PaginationConfig, RetryConfig, SourceConfig


def _source(**overrides):
    defaults = dict(name="fake", base_url="https://fake.test", auth=AuthConfig(type="none"), endpoints=[])
    defaults.update(overrides)
    return SourceConfig(**defaults)


@respx.mock
def test_connector_follows_next_url_pagination_across_pages():
    respx.get("https://fake.test/items", params={}).mock(
        return_value=httpx.Response(200, json={"results": [{"id": 1}], "next": "https://fake.test/items2"})
    )
    respx.get("https://fake.test/items2").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 2}], "next": None})
    )

    source = _source()
    endpoint = EndpointConfig(
        name="items",
        path="/items",
        records_path="results",
        id_field="id",
        pagination=PaginationConfig(type="next_url", next_field="next", max_pages=5),
    )
    connector = GenericApiConnector(source, endpoint)
    try:
        pages = list(connector.fetch_all())
    finally:
        connector.close()

    assert [records for _, records in pages] == [[{"id": 1}], [{"id": 2}]]


@respx.mock
def test_connector_retries_on_500_then_succeeds():
    route = respx.get("https://fake.test/items")
    route.side_effect = [
        httpx.Response(500),
        httpx.Response(200, json={"results": [{"id": 1}], "next": None}),
    ]

    source = _source(retry=RetryConfig(max_attempts=3, backoff_factor=0.01))
    endpoint = EndpointConfig(
        name="items",
        path="/items",
        records_path="results",
        id_field="id",
        pagination=PaginationConfig(type="next_url", next_field="next"),
    )
    connector = GenericApiConnector(source, endpoint)
    try:
        pages = list(connector.fetch_all())
    finally:
        connector.close()

    assert pages[0][1] == [{"id": 1}]
    assert route.call_count == 2


@respx.mock
def test_connector_does_not_retry_on_404():
    respx.get("https://fake.test/items").mock(return_value=httpx.Response(404))

    source = _source(retry=RetryConfig(max_attempts=3, backoff_factor=0.01))
    endpoint = EndpointConfig(
        name="items",
        path="/items",
        records_path="results",
        pagination=PaginationConfig(type="none"),
    )
    connector = GenericApiConnector(source, endpoint)
    try:
        try:
            list(connector.fetch_all())
            assert False, "expected an HTTPStatusError"
        except httpx.HTTPStatusError as exc:
            assert exc.response.status_code == 404
    finally:
        connector.close()

    assert respx.calls.call_count == 1


@respx.mock
def test_connector_applies_bearer_auth_header():
    captured = {}

    def handler(request):
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json=[])

    respx.get("https://fake.test/items").mock(side_effect=handler)

    source = _source(auth=AuthConfig(type="bearer", token_env="TEST_BEARER_TOKEN"))
    endpoint = EndpointConfig(name="items", path="/items", records_path="$", pagination=PaginationConfig(type="none"))

    import os
    os.environ["TEST_BEARER_TOKEN"] = "tok-123"
    try:
        connector = GenericApiConnector(source, endpoint)
        try:
            list(connector.fetch_all())
        finally:
            connector.close()
    finally:
        del os.environ["TEST_BEARER_TOKEN"]

    assert captured["authorization"] == "Bearer tok-123"


@respx.mock
def test_connector_follows_link_header_pagination():
    respx.get("https://fake.test/repos").mock(
        return_value=httpx.Response(
            200, json=[{"id": 1}], headers={"link": '<https://fake.test/repos2>; rel="next"'}
        )
    )
    respx.get("https://fake.test/repos2").mock(return_value=httpx.Response(200, json=[{"id": 2}]))

    source = _source()
    endpoint = EndpointConfig(
        name="repos",
        path="/repos",
        records_path="$",
        id_field="id",
        pagination=PaginationConfig(type="link_header", max_pages=5),
    )
    connector = GenericApiConnector(source, endpoint)
    try:
        pages = list(connector.fetch_all())
    finally:
        connector.close()

    assert [records for _, records in pages] == [[{"id": 1}], [{"id": 2}]]
