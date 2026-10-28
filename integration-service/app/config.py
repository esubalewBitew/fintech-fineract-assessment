from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg2://integration:integration_secret@localhost:5432/integration"
    )
    api_key: str = "integration-key"
    allowed_currency: str = "RWF"

    mock_erp_url: str = "http://localhost:8081"
    mock_erp_api_key: str = "mock-erp-key"
    coa_source_system: str = "mock-erp"

    fineract_base_url: str = "https://localhost:8443/fineract-provider/api/v1"
    fineract_username: str = "mifos"
    fineract_password: str = "password"
    fineract_tenant: str = "default"
    fineract_verify_ssl: bool = False

    default_rail: str = "offline"


settings = Settings()
