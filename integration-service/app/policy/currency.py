from app.config import settings
from app.ports.core_banking import CurrencyRejected


def assert_allowed_currency(currency: str) -> None:
    allowed = settings.allowed_currency.upper()
    if currency.upper() != allowed:
        raise CurrencyRejected(f"currency {currency} rejected; only {allowed} allowed")
