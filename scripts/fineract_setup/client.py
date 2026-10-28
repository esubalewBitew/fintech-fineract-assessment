from __future__ import annotations

import base64
import time
from typing import Any, Optional

import httpx


class FineractHttpClient:
    """Thin Basic-auth client for Fineract REST (assessment bootstrap only)."""

    def __init__(
        self,
        base_url: str,
        *,
        username: str,
        password: str,
        tenant: str = "default",
        verify_ssl: bool = False,
        timeout: float = 60.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "Fineract-Platform-TenantId": tenant,
            "Content-Type": "application/json",
        }
        self._client = httpx.Client(
            verify=verify_ssl,
            timeout=timeout,
            transport=transport,
            headers=self._headers,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FineractHttpClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def wait_until_ready(self, *, attempts: int = 60, sleep_s: float = 2.0) -> None:
        last = None  # type: Optional[Exception]
        for _ in range(attempts):
            try:
                r = self._client.get(f"{self.base_url}/offices")
                if r.status_code < 500:
                    return
                last = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            except Exception as exc:  # noqa: BLE001 — retry until ready
                last = exc
            time.sleep(sleep_s)
        raise RuntimeError(f"Fineract not ready after {attempts} attempts: {last}") from last

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.get(f"{self.base_url}{path}", **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.post(f"{self.base_url}{path}", **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.put(f"{self.base_url}{path}", **kwargs)

    def get_json(self, path: str) -> Any:
        r = self.get(path)
        r.raise_for_status()
        return r.json() if r.content else None

    def post_json(self, path: str, body: dict) -> Any:
        r = self.post(path, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text}")
        return r.json() if r.content else {}

    def put_json(self, path: str, body: dict) -> Any:
        r = self.put(path, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"PUT {path} -> {r.status_code}: {r.text}")
        return r.json() if r.content else {}
