import os
from typing import Any, Optional

import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "10"))


class ApiClientError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


async def _request(
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
) -> Any:
    url = f"{API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await client.request(method, url, json=json)
    except httpx.HTTPError as e:
        raise ApiClientError(f"API request failed: {e}") from e

    try:
        data = response.json()
    except Exception:
        data = {"detail": response.text}

    if response.status_code >= 400:
        message = data.get("detail") or data.get("message") or f"HTTP {response.status_code}"
        raise ApiClientError(message, response.status_code)

    return data


async def get_admin_user_profile(user_id: int) -> dict[str, Any]:
    return await _request("GET", f"/admin/users/{int(user_id)}")


async def get_next_task(user_id: int) -> Optional[dict[str, Any]]:
    try:
        return await _request(
            "GET",
            f"/tasks/bot/next/{int(user_id)}",
        )
    except ApiClientError as e:
        if e.status_code == 404:
            return None
        raise


async def open_task(user_id: int, task_id: int) -> dict[str, Any]:
    return await _request(
        "POST",
        f"/tasks/bot/{int(task_id)}/open/{int(user_id)}",
        json={},
    )


async def check_task(user_id: int, task_id: int) -> dict[str, Any]:
    return await _request(
        "POST",
        f"/tasks/bot/{int(task_id)}/check/{int(user_id)}",
        json={},
    )