"""Loads every *.yaml/*.yml file in a directory as a SourceConfig. This is
the entire "add a new data source" workflow: drop a config file in, restart
(or later, hot-reload) -- no application code changes."""
from pathlib import Path
from typing import Dict

import yaml

from app.schemas import SourceConfig


def load_sources(config_dir: str) -> Dict[str, SourceConfig]:
    sources: Dict[str, SourceConfig] = {}
    directory = Path(config_dir)
    if not directory.is_dir():
        return sources

    paths = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        cfg = SourceConfig(**raw)
        if cfg.name in sources:
            raise ValueError(f"Duplicate source name '{cfg.name}' in {path}")
        sources[cfg.name] = cfg
    return sources
