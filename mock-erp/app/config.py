from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://mock_erp:mock_erp_secret@localhost:5432/mock_erp"
    api_key: str = "mock-erp-key"
    seed_on_startup: bool = True


settings = Settings()
