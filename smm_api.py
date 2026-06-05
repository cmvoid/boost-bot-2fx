"""Client for the standard SMM panel API (PerfectPanel / api/v2 format).

All requests are form-urlencoded POSTs to the same endpoint, with the
`key` and `action` parameters. Responses are JSON.

Supported actions:
  - balance:  {"balance": "100.84", "currency": "USD"}
  - services: [ {service, name, type, rate, min, max, ...}, ... ]
  - add:      {"order": 23501}   or {"error": "..."}
  - status:   {"charge": "0.27", "start_count": "...", "status": "...", "remains": "..."}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx


class SmmApiError(Exception):
    """Error returned by the panel or a communication failure."""


@dataclass
class Balance:
    amount: float
    currency: str


@dataclass
class OrderResult:
    order_id: int


class SmmClient:
    def __init__(self, api_url: str, api_key: str, timeout: float = 30.0):
        self._api_url = api_url
        self._api_key = api_key
        self._timeout = timeout

    async def _post(self, payload: dict[str, Any]) -> Any:
        data = {"key": self._api_key, **payload}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._api_url, data=data)
        except httpx.HTTPError as exc:
            raise SmmApiError(f"Connection error to the panel: {exc}") from exc

        if resp.status_code != 200:
            raise SmmApiError(
                f"The panel responded with HTTP {resp.status_code}. "
                "Check that SMM_API_URL is correct (it usually ends with /api/v2)."
            )

        try:
            result = resp.json()
        except ValueError:
            snippet = resp.text[:200]
            raise SmmApiError(
                "Non-JSON response from the panel. "
                f"Verify the API URL. Start of response: {snippet!r}"
            )

        if isinstance(result, dict) and result.get("error"):
            raise SmmApiError(str(result["error"]))

        return result

    async def get_balance(self) -> Balance:
        result = await self._post({"action": "balance"})
        if not isinstance(result, dict) or "balance" not in result:
            raise SmmApiError(f"Unexpected balance response: {result!r}")
        try:
            amount = float(result["balance"])
        except (TypeError, ValueError):
            raise SmmApiError(f"Non-numeric balance: {result.get('balance')!r}")
        return Balance(amount=amount, currency=str(result.get("currency", "")).strip())

    async def get_services(self) -> list[dict[str, Any]]:
        result = await self._post({"action": "services"})
        if not isinstance(result, list):
            raise SmmApiError(f"Unexpected services response: {result!r}")
        return result

    async def add_order(self, service_id: int, link: str, quantity: int) -> OrderResult:
        result = await self._post(
            {
                "action": "add",
                "service": service_id,
                "link": link,
                "quantity": quantity,
            }
        )
        if not isinstance(result, dict) or "order" not in result:
            raise SmmApiError(f"Unexpected order response: {result!r}")
        return OrderResult(order_id=int(result["order"]))

    async def get_status(self, order_id: int) -> dict[str, Any]:
        result = await self._post({"action": "status", "order": order_id})
        if not isinstance(result, dict):
            raise SmmApiError(f"Unexpected status response: {result!r}")
        return result
