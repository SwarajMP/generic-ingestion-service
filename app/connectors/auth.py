"""Auth strategies. Each one is a pure function over (params, headers) that
returns new (params, headers) — no mutation of shared state, so the same
strategy instance can be reused across every page of a paginated pull."""
import base64
import os
from abc import ABC, abstractmethod
from typing import Dict, Tuple

from app.schemas import AuthConfig


class AuthStrategy(ABC):
    @abstractmethod
    def apply(self, params: Dict, headers: Dict) -> Tuple[Dict, Dict]:
        ...


class NoAuth(AuthStrategy):
    def apply(self, params, headers):
        return params, headers


class ApiKeyQueryAuth(AuthStrategy):
    def __init__(self, param_name: str, key: str):
        self.param_name = param_name
        self.key = key

    def apply(self, params, headers):
        if not self.key:
            return params, headers
        return {**params, self.param_name: self.key}, headers


class ApiKeyHeaderAuth(AuthStrategy):
    def __init__(self, header_name: str, key: str):
        self.header_name = header_name
        self.key = key

    def apply(self, params, headers):
        if not self.key:
            return params, headers
        return params, {**headers, self.header_name: self.key}


class BearerTokenAuth(AuthStrategy):
    def __init__(self, token: str):
        self.token = token

    def apply(self, params, headers):
        if not self.token:
            return params, headers
        return params, {**headers, "Authorization": f"Bearer {self.token}"}


class BasicAuth(AuthStrategy):
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def apply(self, params, headers):
        creds = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        return params, {**headers, "Authorization": f"Basic {creds}"}


def build_auth_strategy(cfg: AuthConfig) -> AuthStrategy:
    if cfg.type == "none":
        return NoAuth()
    if cfg.type == "api_key_query":
        key = os.environ.get(cfg.token_env, "") if cfg.token_env else ""
        return ApiKeyQueryAuth(cfg.param_name or "api_key", key)
    if cfg.type == "api_key_header":
        key = os.environ.get(cfg.token_env, "") if cfg.token_env else ""
        return ApiKeyHeaderAuth(cfg.header_name or "X-API-Key", key)
    if cfg.type == "bearer":
        token = os.environ.get(cfg.token_env, "") if cfg.token_env else ""
        return BearerTokenAuth(token)
    if cfg.type == "basic":
        username = os.environ.get(cfg.username_env, "") if cfg.username_env else ""
        password = os.environ.get(cfg.password_env, "") if cfg.password_env else ""
        return BasicAuth(username, password)
    raise ValueError(f"Unsupported auth type: {cfg.type}")
