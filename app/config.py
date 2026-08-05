from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://ingestion:ingestion@localhost:5432/ingestion"
    sources_config_dir: str = "sources_config"
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Managed Postgres providers (Render, Heroku, ...) hand back a bare
        'postgres://' or driver-less 'postgresql://' URL; SQLAlchemy 2.x
        needs the psycopg2 dialect spelled out explicitly."""
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://") and "+psycopg2" not in v:
            v = v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v


settings = Settings()
