from app.connectors.auth import build_auth_strategy
from app.schemas import AuthConfig


def test_no_auth_passthrough():
    strategy = build_auth_strategy(AuthConfig(type="none"))
    params, headers = strategy.apply({"a": 1}, {"h": "v"})
    assert params == {"a": 1}
    assert headers == {"h": "v"}


def test_api_key_query_reads_env_and_injects_param(monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret123")
    strategy = build_auth_strategy(AuthConfig(type="api_key_query", param_name="apikey", token_env="MY_KEY"))
    params, headers = strategy.apply({}, {})
    assert params == {"apikey": "secret123"}
    assert headers == {}


def test_api_key_header_injects_header(monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret123")
    strategy = build_auth_strategy(AuthConfig(type="api_key_header", header_name="X-Api-Key", token_env="MY_KEY"))
    params, headers = strategy.apply({}, {})
    assert headers == {"X-Api-Key": "secret123"}


def test_bearer_auth_sets_authorization_header(monkeypatch):
    monkeypatch.setenv("TOKEN", "abc")
    strategy = build_auth_strategy(AuthConfig(type="bearer", token_env="TOKEN"))
    params, headers = strategy.apply({}, {})
    assert headers["Authorization"] == "Bearer abc"


def test_bearer_auth_without_token_omits_header(monkeypatch):
    monkeypatch.delenv("MISSING_ENV_VAR", raising=False)
    strategy = build_auth_strategy(AuthConfig(type="bearer", token_env="MISSING_ENV_VAR"))
    params, headers = strategy.apply({}, {})
    assert "Authorization" not in headers


def test_basic_auth_encodes_credentials(monkeypatch):
    monkeypatch.setenv("U", "user")
    monkeypatch.setenv("P", "pass")
    strategy = build_auth_strategy(AuthConfig(type="basic", username_env="U", password_env="P"))
    params, headers = strategy.apply({}, {})
    assert headers["Authorization"] == "Basic dXNlcjpwYXNz"


def test_original_dicts_are_not_mutated(monkeypatch):
    monkeypatch.setenv("TOKEN", "abc")
    strategy = build_auth_strategy(AuthConfig(type="bearer", token_env="TOKEN"))
    original_headers = {"X-Existing": "1"}
    _, new_headers = strategy.apply({}, original_headers)
    assert original_headers == {"X-Existing": "1"}
    assert new_headers != original_headers
