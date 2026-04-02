from __future__ import annotations

from typing import Any, Optional

import httpx

from shared.config import (
    API_BASE_URL as SHARED_API_BASE_URL,
    API_TIMEOUT as SHARED_API_TIMEOUT,
    BOT_INTERNAL_TOKEN,
)

JsonDict = dict[str, Any]

API_BASE_URL = SHARED_API_BASE_URL or "http://127.0.0.1:8000"
API_TIMEOUT = float(SHARED_API_TIMEOUT or 10)


class ApiClientError(Exception):
    def __init__(
            self,
            message: str,
            status_code: Optional[int] = None,
            *,
            method: Optional[str] = None,
            path: Optional[str] = None,
            detail: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.method = method
        self.path = path
        self.detail = detail or message


class ApiSection:
    def __init__(self, client: "BotApiClient"):
        self._client = client

    async def _request(
            self,
            method: str,
            path: str,
            *,
            json: Optional[JsonDict] = None,
            params: Optional[JsonDict] = None,
            allow_not_found: bool = False,
    ) -> Any:
        return await self._client._request(
            method,
            path,
            json=json,
            params=params,
            allow_not_found=allow_not_found,
        )

    async def _get(
            self,
            path: str,
            *,
            params: Optional[JsonDict] = None,
            allow_not_found: bool = False,
    ) -> Any:
        return await self._request(
            "GET",
            path,
            params=params,
            allow_not_found=allow_not_found,
        )

    async def _post(
            self,
            path: str,
            *,
            json: Optional[JsonDict] = None,
            allow_not_found: bool = False,
    ) -> Any:
        return await self._request(
            "POST",
            path,
            json=json,
            allow_not_found=allow_not_found,
        )


class ProfileApi(ApiSection):
    async def bootstrap_user(
            self,
            *,
            user_id: int,
            username: Optional[str],
            first_name: Optional[str],
            last_name: Optional[str],
            start_referrer_id: Optional[int] = None,
    ) -> JsonDict:
        return await self._post(
            "/bot/users/bootstrap",
            json={
                "user": {
                    "user_id": int(user_id),
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                },
                "start_referrer_id": start_referrer_id,
            },
        )

    async def get_main_menu_for_user_context(
            self,
            *,
            user_id: int,
            username: Optional[str],
            first_name: Optional[str],
            last_name: Optional[str],
    ) -> JsonDict:
        return await self._post(
            "/bot/users/main-menu",
            json={
                "user": {
                    "user_id": int(user_id),
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                },
            },
        )

    async def get_main_menu(self, user_id: int) -> JsonDict:
        return await self._get(f"/bot/users/{int(user_id)}/main-menu")


class CampaignsApi(ApiSection):
    async def list_active(self) -> JsonDict:
        return await self._get("/campaigns/bot/active")

    async def claim(
            self,
            user_id: int,
            campaign_key: str,
            *,
            username: Optional[str],
            first_name: Optional[str],
            last_name: Optional[str],
    ) -> JsonDict:
        return await self._post(
            f"/campaigns/bot/{campaign_key}/claim/{int(user_id)}",
            json={
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
            },
        )


class TasksApi(ApiSection):
    async def get_next(self, user_id: int) -> Optional[JsonDict]:
        return await self._get(
            f"/tasks/bot/next/{int(user_id)}",
            allow_not_found=True,
        )

    async def open(self, user_id: int, task_id: int) -> JsonDict:
        return await self._post(
            f"/tasks/bot/{int(task_id)}/open/{int(user_id)}",
            json={},
        )

    async def check(self, user_id: int, task_id: int) -> JsonDict:
        return await self._post(
            f"/tasks/bot/{int(task_id)}/check/{int(user_id)}",
            json={},
        )


class CheckinApi(ApiSection):
    async def get_status(
            self,
            user_id: int,
            *,
            username: Optional[str] = None,
            first_name: Optional[str] = None,
            last_name: Optional[str] = None,
    ) -> JsonDict:
        if username is None and first_name is None and last_name is None:
            return await self._get(f"/checkin/bot/status/{int(user_id)}")

        return await self._post(
            "/checkin/bot/status",
            json={
                "user": {
                    "user_id": int(user_id),
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                }
            },
        )

    async def claim(
            self,
            user_id: int,
            *,
            username: Optional[str] = None,
            first_name: Optional[str] = None,
            last_name: Optional[str] = None,
    ) -> JsonDict:
        if username is None and first_name is None and last_name is None:
            return await self._post(
                f"/checkin/bot/claim/{int(user_id)}",
                json={},
            )

        return await self._post(
            "/checkin/bot/claim",
            json={
                "user": {
                    "user_id": int(user_id),
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                }
            },
        )


class LedgerApi(ApiSection):
    async def list(self, user_id: int, limit: int = 20) -> JsonDict:
        return await self._get(
            f"/ledger/bot/{int(user_id)}",
            params={"limit": limit},
        )

    async def get_sum(self, user_id: int) -> JsonDict:
        return await self._get(f"/ledger/bot/{int(user_id)}/sum")


class WithdrawalsApi(ApiSection):
    async def get_eligibility(self, user_id: int) -> JsonDict:
        return await self._get(
            f"/withdrawals/bot/eligibility/{int(user_id)}",
        )

    async def preview(self, user_id: int, payload: JsonDict) -> JsonDict:
        return await self._post(
            f"/withdrawals/bot/preview/{int(user_id)}",
            json=payload,
        )

    async def list_my(self, user_id: int, limit: int = 20) -> JsonDict:
        return await self._get(
            f"/withdrawals/bot/my/{int(user_id)}",
            params={"limit": limit},
        )

    async def create(self, user_id: int, payload: JsonDict) -> JsonDict:
        return await self._post(
            f"/withdrawals/bot/create/{int(user_id)}",
            json=payload,
        )


class UsersApi(ApiSection):
    async def lookup(self, query: str) -> JsonDict:
        return await self._post(
            "/admin/users/lookup",
            json={"query": query},
        )

    async def get_profile(self, user_id: int) -> JsonDict:
        return await self._get(f"/admin/users/{int(user_id)}")

    async def set_role(self, user_id: int, role_level: int) -> JsonDict:
        return await self._post(
            f"/admin/users/{int(user_id)}/role",
            json={"role_level": int(role_level)},
        )

    async def adjust_balance(
            self,
            user_id: int,
            *,
            amount: float,
            mode: str,
    ) -> JsonDict:
        return await self._post(
            f"/admin/users/{int(user_id)}/balance-adjust",
            json={
                "amount": float(amount),
                "mode": mode,
            },
        )

    async def mark_suspicious(self, user_id: int, reason: Optional[str] = None) -> JsonDict:
        return await self._post(
            f"/admin/users/{int(user_id)}/mark-suspicious",
            json={"reason": reason},
        )

    async def clear_suspicious(self, user_id: int) -> JsonDict:
        return await self._post(
            f"/admin/users/{int(user_id)}/clear-suspicious",
            json={},
        )


class AdminCampaignsApi(ApiSection):
    """
    Reserved for admin campaign endpoints.
    Admin UI stays in Telegram bot, while business logic will move to API gradually.
    """


class AdminTaskChannelsApi(ApiSection):
    """
    Reserved for admin task-channel endpoints.
    Admin UI stays in Telegram bot, while business logic will move to API gradually.
    """


class BotApiClient:
    def __init__(
            self,
            *,
            base_url: str,
            timeout: float,
            internal_token: Optional[str],
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.internal_token = internal_token

        self.profile = ProfileApi(self)
        self.campaigns = CampaignsApi(self)
        self.tasks = TasksApi(self)
        self.checkin = CheckinApi(self)
        self.ledger = LedgerApi(self)
        self.withdrawals = WithdrawalsApi(self)
        self.users = UsersApi(self)
        self.admin_campaigns = AdminCampaignsApi(self)
        self.admin_task_channels = AdminTaskChannelsApi(self)

    def _build_headers(self) -> dict[str, str]:
        if not self.internal_token:
            raise ApiClientError("BOT_INTERNAL_TOKEN is not configured")

        return {
            "X-Internal-Token": self.internal_token,
        }

    @staticmethod
    def _extract_error_detail(response: httpx.Response, data: Any) -> str:
        if isinstance(data, dict):
            detail = data.get("detail") or data.get("message")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
        text = (response.text or "").strip()
        if text:
            return text
        return f"HTTP {response.status_code}"

    async def _request(
            self,
            method: str,
            path: str,
            *,
            json: Optional[JsonDict] = None,
            params: Optional[JsonDict] = None,
            allow_not_found: bool = False,
    ) -> Any:
        normalized_path = f"/{path.lstrip('/')}"
        url = f"{self.base_url}{normalized_path}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                    headers=self._build_headers(),
                )
        except httpx.HTTPError as e:
            raise ApiClientError(
                f"{method} {normalized_path} failed: {e}",
                method=method,
                path=normalized_path,
            ) from e

        try:
            data = response.json()
        except Exception:
            data = None

        if allow_not_found and response.status_code == 404:
            return None

        if response.status_code >= 400:
            detail = self._extract_error_detail(response, data)
            raise ApiClientError(
                f"{method} {normalized_path} returned {response.status_code}: {detail}",
                response.status_code,
                method=method,
                path=normalized_path,
                detail=detail,
            )

        return data


api_client = BotApiClient(
    base_url=API_BASE_URL,
    timeout=API_TIMEOUT,
    internal_token=BOT_INTERNAL_TOKEN,
)


async def get_user_profile(user_id: int) -> JsonDict:
    return await api_client.users.get_profile(user_id)


async def lookup_user(query: str) -> JsonDict:
    return await api_client.users.lookup(query)


async def set_user_role(user_id: int, role_level: int) -> JsonDict:
    return await api_client.users.set_role(user_id, role_level)


async def adjust_user_balance(
        user_id: int,
        *,
        amount: float,
        mode: str,
) -> JsonDict:
    return await api_client.users.adjust_balance(
        user_id,
        amount=amount,
        mode=mode,
    )


async def mark_user_suspicious(user_id: int, reason: Optional[str] = None) -> JsonDict:
    return await api_client.users.mark_suspicious(user_id, reason=reason)


async def clear_user_suspicious(user_id: int) -> JsonDict:
    return await api_client.users.clear_suspicious(user_id)


async def get_active_campaigns_via_api() -> JsonDict:
    return await api_client.campaigns.list_active()


async def claim_campaign_reward_via_api(
        *,
        user_id: int,
        campaign_key: str,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
) -> JsonDict:
    return await api_client.campaigns.claim(
        user_id=user_id,
        campaign_key=campaign_key,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )


async def bootstrap_bot_user_via_api(
        *,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        start_referrer_id: Optional[int] = None,
) -> JsonDict:
    return await api_client.profile.bootstrap_user(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        start_referrer_id=start_referrer_id,
    )


async def get_bot_main_menu_for_user_context_via_api(
        *,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
) -> JsonDict:
    return await api_client.profile.get_main_menu_for_user_context(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )


async def get_bot_main_menu_via_api(user_id: int) -> JsonDict:
    return await api_client.profile.get_main_menu(user_id)


async def get_next_task(user_id: int) -> Optional[JsonDict]:
    return await api_client.tasks.get_next(user_id)


async def open_task(user_id: int, task_id: int) -> JsonDict:
    return await api_client.tasks.open(user_id, task_id)


async def check_task(user_id: int, task_id: int) -> JsonDict:
    return await api_client.tasks.check(user_id, task_id)


async def get_daily_checkin_status(
        user_id: int,
        *,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> JsonDict:
    return await api_client.checkin.get_status(
        user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )


async def claim_daily_checkin_via_api(
        user_id: int,
        *,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> JsonDict:
    return await api_client.checkin.claim(
        user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )


async def get_ledger(user_id: int, limit: int = 20) -> JsonDict:
    return await api_client.ledger.list(user_id, limit=limit)


async def get_ledger_sum(user_id: int) -> JsonDict:
    return await api_client.ledger.get_sum(user_id)


async def get_withdrawal_eligibility_via_api(user_id: int) -> JsonDict:
    return await api_client.withdrawals.get_eligibility(user_id)


async def preview_withdrawal_via_api(user_id: int, payload: JsonDict) -> JsonDict:
    return await api_client.withdrawals.preview(user_id, payload)


async def get_my_withdrawals_via_api(user_id: int, limit: int = 20) -> JsonDict:
    return await api_client.withdrawals.list_my(user_id, limit=limit)


async def create_withdrawal_via_api(user_id: int, payload: JsonDict) -> JsonDict:
    return await api_client.withdrawals.create(user_id, payload)


__all__ = [
    "ApiClientError",
    "BotApiClient",
    "api_client",
    "get_user_profile",
    "lookup_user",
    "set_user_role",
    "adjust_user_balance",
    "mark_user_suspicious",
    "clear_user_suspicious",
    "get_active_campaigns_via_api",
    "claim_campaign_reward_via_api",
    "bootstrap_bot_user_via_api",
    "get_bot_main_menu_for_user_context_via_api",
    "get_bot_main_menu_via_api",
    "get_next_task",
    "open_task",
    "check_task",
    "get_daily_checkin_status",
    "claim_daily_checkin_via_api",
    "get_ledger",
    "get_ledger_sum",
    "get_withdrawal_eligibility_via_api",
    "preview_withdrawal_via_api",
    "get_my_withdrawals_via_api",
    "create_withdrawal_via_api",
]
