from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://ingestion:ingestion@localhost:5432/ingestion"
    sources_config_dir: str = "sources_config"
    log_level: str = "INFO"


settings = Settings()
