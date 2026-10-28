from typing import Protocol

from app.domain.models import CoAAccount


class CoAProviderPort(Protocol):
    source_system: str

    def list_accounts(self) -> list[CoAAccount]: ...
