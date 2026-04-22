from __future__ import annotations

from typing import Any, Optional, Sequence

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

    async def check(self, user_id: int, task_id: int, *, session_id: Optional[str] = None) -> JsonDict:
        return await self._post(
            f"/tasks/bot/{int(task_id)}/check/{int(user_id)}",
            json={"session_id": session_id},
        )

    async def ingest_channel_post(
            self,
            *,
            chat_id: str,
            channel_post_id: int,
            title: Optional[str],
            reward: float = 0.01,
    ) -> JsonDict:
        return await self._post(
            "/tasks/bot/channel-posts/ingest",
            json={
                "chat_id": str(chat_id),
                "channel_post_id": int(channel_post_id),
                "title": title,
                "reward": float(reward),
            },
        )

    async def report_unavailable(self, user_id: int, task_id: int, *, reason: Optional[str] = None) -> JsonDict:
        return await self._post(
            f"/tasks/bot/{int(task_id)}/unavailable/{int(user_id)}",
            json={"reason": reason},
        )


class BattlesApi(ApiSection):
    async def get_status(self, user_id: int) -> JsonDict:
        return await self._get(f"/battles/bot/me/{int(user_id)}")


class TheftsApi(ApiSection):
    async def get_status(self, user_id: int) -> JsonDict:
        return await self._get(f"/thefts/bot/me/{int(user_id)}")


class UsersApi(ApiSection):
    async def lookup(self, query: str) -> JsonDict:
        return await self._post(
            "/admin/users/lookup",
            json={"query": query},
        )

    async def get_profile(self, user_id: int) -> JsonDict:
        return await self._get(f"/admin/users/{int(user_id)}")

    async def get_stats(self, user_id: int) -> JsonDict:
        return await self._get(f"/admin/users/{int(user_id)}/stats")

    async def get_battle_stats(self, user_id: int) -> JsonDict:
        return await self._get(f"/admin/users/{int(user_id)}/battle-stats")

    async def get_theft_stats(self, user_id: int) -> JsonDict:
        return await self._get(f"/admin/users/{int(user_id)}/theft-stats")

    async def get_ledger(
            self,
            user_id: int,
            *,
            page: int = 0,
            page_size: int = 20,
    ) -> JsonDict:
        return await self._get(
            f"/admin/users/{int(user_id)}/ledger",
            params={
                "page": int(page),
                "page_size": int(page_size),
            },
        )

    async def get_risk(
            self,
            user_id: int,
            *,
            page: int = 0,
            page_size: int = 20,
    ) -> JsonDict:
        return await self._get(
            f"/admin/users/{int(user_id)}/risk",
            params={
                "page": int(page),
                "page_size": int(page_size),
            },
        )

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


class ReviewWithdrawalsApi(ApiSection):
    async def list(self, *, status: str = "pending", limit: int = 20) -> JsonDict:
        return await self._get(
            "/admin/withdrawals",
            params={
                "status": status,
                "limit": int(limit),
            },
        )

    async def get(self, withdrawal_id: int) -> JsonDict:
        return await self._get(f"/admin/withdrawals/{int(withdrawal_id)}")

    async def mark_paid(self, withdrawal_id: int, *, admin_id: int) -> JsonDict:
        return await self._post(
            f"/admin/withdrawals/{int(withdrawal_id)}/mark-paid",
            json={"admin_id": int(admin_id)},
        )

    async def reject(self, withdrawal_id: int, *, admin_id: int) -> JsonDict:
        return await self._post(
            f"/admin/withdrawals/{int(withdrawal_id)}/reject",
            json={"admin_id": int(admin_id)},
        )

    async def list_recent_fee_payments(self, *, limit: int = 10) -> JsonDict:
        return await self._get(
            "/admin/withdrawals/fee-payments/recent",
            params={"limit": int(limit)},
        )

    async def record_fee_refund(
            self,
            withdrawal_id: int,
            *,
            meta: Optional[str] = None,
    ) -> JsonDict:
        return await self._post(
            f"/admin/withdrawals/{int(withdrawal_id)}/fee-refund",
            json={"meta": meta},
        )

    async def record_fee_refund_by_charge_id(
            self,
            charge_id: str,
            *,
            meta: Optional[str] = None,
    ) -> JsonDict:
        return await self._post(
            "/admin/withdrawals/fee-refunds/by-charge-id",
            json={
                "charge_id": charge_id,
                "meta": meta,
            },
        )


class CampaignsAdminApi(ApiSection):
    async def list(self) -> JsonDict:
        return await self._get("/admin/campaigns")

    async def get(self, campaign_key: str) -> JsonDict:
        return await self._get(f"/admin/campaigns/{campaign_key}")

    async def create(
            self,
            *,
            campaign_key: str,
            title: str,
            amount: float,
            post_url: Optional[str] = None,
    ) -> JsonDict:
        return await self._post(
            "/admin/campaigns",
            json={
                "campaign_key": campaign_key,
                "title": title,
                "amount": float(amount),
                "post_url": post_url,
            },
        )

    async def set_status(self, campaign_key: str, *, status: str) -> JsonDict:
        return await self._post(
            f"/admin/campaigns/{campaign_key}/status",
            json={"status": status},
        )

    async def delete(self, campaign_key: str) -> JsonDict:
        return await self._post(f"/admin/campaigns/{campaign_key}/delete", json={})

    async def add_winners(self, campaign_key: str, *, usernames: Sequence[str]) -> JsonDict:
        return await self._post(
            f"/admin/campaigns/{campaign_key}/winners",
            json={"usernames": list(usernames)},
        )

    async def get_summary(self, *, latest_limit: int = 5) -> JsonDict:
        return await self._get(
            "/admin/campaigns/summary",
            params={"latest_limit": int(latest_limit)},
        )

    async def get_stats(self, campaign_key: str) -> JsonDict:
        return await self._get(f"/admin/campaigns/{campaign_key}/stats")

    async def get_winners(self, campaign_key: str) -> JsonDict:
        return await self._get(f"/admin/campaigns/{campaign_key}/winners")

    async def delete_winner(self, campaign_key: str, *, username: str) -> JsonDict:
        return await self._post(
            f"/admin/campaigns/{campaign_key}/winners/delete",
            json={"username": username},
        )


class PromosAdminApi(ApiSection):
    async def list(self) -> JsonDict:
        return await self._get("/admin/promos")

    async def get(self, promo_code: str) -> JsonDict:
        return await self._get(f"/admin/promos/{promo_code}")

    async def create(
            self,
            *,
            promo_code: str,
            title: Optional[str],
            amount: float,
            total_uses: int,
    ) -> JsonDict:
        return await self._post(
            "/admin/promos",
            json={
                "promo_code": promo_code,
                "title": title,
                "amount": float(amount),
                "total_uses": int(total_uses),
            },
        )

    async def set_status(self, promo_code: str, *, status: str) -> JsonDict:
        return await self._post(
            f"/admin/promos/{promo_code}/status",
            json={"status": status},
        )

    async def delete(self, promo_code: str) -> JsonDict:
        return await self._post(f"/admin/promos/{promo_code}/delete", json={})

    async def get_summary(self, *, latest_limit: int = 5) -> JsonDict:
        return await self._get(
            "/admin/promos/summary",
            params={"latest_limit": int(latest_limit)},
        )

    async def get_stats(self, promo_code: str) -> JsonDict:
        return await self._get(f"/admin/promos/{promo_code}/stats")


class TaskChannelsApi(ApiSection):
    async def list(self) -> JsonDict:
        return await self._get("/admin/task-channels")

    async def get(self, channel_id: int) -> JsonDict:
        return await self._get(f"/admin/task-channels/{int(channel_id)}")

    async def create(
            self,
            *,
            chat_id: str,
            title: Optional[str],
            client_user_id: Optional[int],
            total_bought_views: int,
            views_per_post: int,
            view_seconds: int,
    ) -> JsonDict:
        return await self._post(
            "/admin/task-channels",
            json={
                "chat_id": chat_id,
                "title": title,
                "client_user_id": int(client_user_id) if client_user_id is not None else None,
                "total_bought_views": int(total_bought_views),
                "views_per_post": int(views_per_post),
                "view_seconds": int(view_seconds),
            },
        )

    async def toggle(self, channel_id: int) -> JsonDict:
        return await self._post(f"/admin/task-channels/{int(channel_id)}/toggle", json={})

    async def update_params(
            self,
            channel_id: int,
            *,
            total_bought_views: int,
            views_per_post: int,
            view_seconds: int,
    ) -> JsonDict:
        return await self._post(
            f"/admin/task-channels/{int(channel_id)}/params",
            json={
                "total_bought_views": int(total_bought_views),
                "views_per_post": int(views_per_post),
                "view_seconds": int(view_seconds),
            },
        )

    async def bind_client(self, channel_id: int, *, client_user_id: int) -> JsonDict:
        return await self._post(
            f"/admin/task-channels/{int(channel_id)}/client",
            json={
                "client_user_id": int(client_user_id),
            },
        )

    async def get_posts(self, channel_id: int, *, limit: int = 20) -> JsonDict:
        return await self._get(
            f"/admin/task-channels/{int(channel_id)}/posts",
            params={"limit": int(limit)},
        )


class AnalyticsApi(ApiSection):
    async def get_top_balances(self, *, limit: int = 10) -> JsonDict:
        return await self._get(
            "/admin/analytics/top-balances",
            params={"limit": int(limit)},
        )

    async def get_growth(self, *, days: int = 30) -> JsonDict:
        return await self._get(
            "/admin/analytics/growth",
            params={"days": int(days)},
        )

    async def get_ledger_page(
            self,
            *,
            page: int = 0,
            page_size: int = 20,
    ) -> JsonDict:
        return await self._get(
            "/admin/analytics/ledger",
            params={
                "page": int(page),
                "page_size": int(page_size),
            },
        )

    async def get_audit(self, *, limit: int = 10) -> JsonDict:
        return await self._get(
            "/admin/analytics/audit",
            params={"limit": int(limit)},
        )


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
        self.tasks = TasksApi(self)
        self.battles = BattlesApi(self)
        self.users = UsersApi(self)
        self.withdrawals_review = ReviewWithdrawalsApi(self)
        self.admin_campaigns = CampaignsAdminApi(self)
        self.admin_promos = PromosAdminApi(self)
        self.task_channels = TaskChannelsApi(self)
        self.analytics = AnalyticsApi(self)
        self.thefts = TheftsApi(self)

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


async def get_user_stats(user_id: int) -> JsonDict:
    return await api_client.users.get_stats(user_id)


async def get_user_battle_stats(user_id: int) -> JsonDict:
    return await api_client.users.get_battle_stats(user_id)


async def get_user_theft_stats(user_id: int) -> JsonDict:
    return await api_client.users.get_theft_stats(user_id)


async def get_user_ledger_page(
        user_id: int,
        *,
        page: int = 0,
        page_size: int = 20,
) -> JsonDict:
    return await api_client.users.get_ledger(
        user_id,
        page=page,
        page_size=page_size,
    )


async def get_user_risk_page(
        user_id: int,
        *,
        page: int = 0,
        page_size: int = 20,
) -> JsonDict:
    return await api_client.users.get_risk(
        user_id,
        page=page,
        page_size=page_size,
    )


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


async def list_campaigns_via_api() -> JsonDict:
    return await api_client.admin_campaigns.list()


async def get_campaign_via_api(campaign_key: str) -> JsonDict:
    return await api_client.admin_campaigns.get(campaign_key)


async def create_campaign_via_api(
        *,
        campaign_key: str,
        title: str,
        amount: float,
        post_url: Optional[str] = None,
) -> JsonDict:
    return await api_client.admin_campaigns.create(
        campaign_key=campaign_key,
        title=title,
        amount=amount,
        post_url=post_url,
    )


async def set_campaign_status_via_api(campaign_key: str, *, status: str) -> JsonDict:
    return await api_client.admin_campaigns.set_status(campaign_key, status=status)


async def delete_campaign_via_api(campaign_key: str) -> JsonDict:
    return await api_client.admin_campaigns.delete(campaign_key)


async def add_campaign_winners_via_api(campaign_key: str, usernames: Sequence[str]) -> JsonDict:
    return await api_client.admin_campaigns.add_winners(campaign_key, usernames=usernames)


async def get_campaigns_summary_via_api(*, latest_limit: int = 5) -> JsonDict:
    return await api_client.admin_campaigns.get_summary(latest_limit=latest_limit)


async def get_campaign_stats_via_api(campaign_key: str) -> JsonDict:
    return await api_client.admin_campaigns.get_stats(campaign_key)


async def get_campaign_winners_via_api(campaign_key: str) -> JsonDict:
    return await api_client.admin_campaigns.get_winners(campaign_key)


async def delete_campaign_winner_via_api(campaign_key: str, *, username: str) -> JsonDict:
    return await api_client.admin_campaigns.delete_winner(campaign_key, username=username)


async def list_promos_via_api() -> JsonDict:
    return await api_client.admin_promos.list()


async def get_promo_via_api(promo_code: str) -> JsonDict:
    return await api_client.admin_promos.get(promo_code)


async def create_promo_via_api(
        *,
        promo_code: str,
        title: Optional[str],
        amount: float,
        total_uses: int,
) -> JsonDict:
    return await api_client.admin_promos.create(
        promo_code=promo_code,
        title=title,
        amount=amount,
        total_uses=total_uses,
    )


async def set_promo_status_via_api(promo_code: str, *, status: str) -> JsonDict:
    return await api_client.admin_promos.set_status(promo_code, status=status)


async def delete_promo_via_api(promo_code: str) -> JsonDict:
    return await api_client.admin_promos.delete(promo_code)


async def get_promos_summary_via_api(*, latest_limit: int = 5) -> JsonDict:
    return await api_client.admin_promos.get_summary(latest_limit=latest_limit)


async def get_promo_stats_via_api(promo_code: str) -> JsonDict:
    return await api_client.admin_promos.get_stats(promo_code)


async def get_top_balances_via_api(*, limit: int = 10) -> JsonDict:
    return await api_client.analytics.get_top_balances(limit=limit)


async def get_growth_via_api(*, days: int = 30) -> JsonDict:
    return await api_client.analytics.get_growth(days=days)


async def get_admin_ledger_page_via_api(
        *,
        page: int = 0,
        page_size: int = 20,
) -> JsonDict:
    return await api_client.analytics.get_ledger_page(page=page, page_size=page_size)


async def get_audit_via_api(*, limit: int = 10) -> JsonDict:
    return await api_client.analytics.get_audit(limit=limit)


async def list_withdrawals_queue(*, status: str = "pending", limit: int = 20) -> JsonDict:
    return await api_client.withdrawals_review.list(status=status, limit=limit)


async def get_withdrawal_details(withdrawal_id: int) -> JsonDict:
    return await api_client.withdrawals_review.get(withdrawal_id)


async def mark_withdrawal_paid(withdrawal_id: int, *, admin_id: int) -> JsonDict:
    return await api_client.withdrawals_review.mark_paid(withdrawal_id, admin_id=admin_id)


async def reject_withdrawal(withdrawal_id: int, *, admin_id: int) -> JsonDict:
    return await api_client.withdrawals_review.reject(withdrawal_id, admin_id=admin_id)


async def list_recent_fee_payments_via_api(*, limit: int = 10) -> JsonDict:
    return await api_client.withdrawals_review.list_recent_fee_payments(limit=limit)


async def record_withdrawal_fee_refund(
        withdrawal_id: int,
        *,
        meta: Optional[str] = None,
) -> JsonDict:
    return await api_client.withdrawals_review.record_fee_refund(
        withdrawal_id,
        meta=meta,
    )


async def record_fee_refund_by_charge_id(
        charge_id: str,
        *,
        meta: Optional[str] = None,
) -> JsonDict:
    return await api_client.withdrawals_review.record_fee_refund_by_charge_id(
        charge_id,
        meta=meta,
    )


async def list_task_channels_via_api() -> JsonDict:
    return await api_client.task_channels.list()


async def get_task_channel_via_api(channel_id: int) -> JsonDict:
    return await api_client.task_channels.get(channel_id)


async def create_task_channel_via_api(
        *,
        chat_id: str,
        title: Optional[str],
        client_user_id: Optional[int],
        total_bought_views: int,
        views_per_post: int,
        view_seconds: int,
) -> JsonDict:
    return await api_client.task_channels.create(
        chat_id=chat_id,
        title=title,
        client_user_id=client_user_id,
        total_bought_views=total_bought_views,
        views_per_post=views_per_post,
        view_seconds=view_seconds,
    )


async def toggle_task_channel_via_api(channel_id: int) -> JsonDict:
    return await api_client.task_channels.toggle(channel_id)


async def update_task_channel_params_via_api(
        channel_id: int,
        *,
        total_bought_views: int,
        views_per_post: int,
        view_seconds: int,
) -> JsonDict:
    return await api_client.task_channels.update_params(
        channel_id,
        total_bought_views=total_bought_views,
        views_per_post=views_per_post,
        view_seconds=view_seconds,
    )


async def bind_task_channel_client_via_api(
        channel_id: int,
        *,
        client_user_id: int,
) -> JsonDict:
    return await api_client.task_channels.bind_client(
        channel_id,
        client_user_id=client_user_id,
    )


async def get_task_channel_posts_via_api(channel_id: int, *, limit: int = 20) -> JsonDict:
    return await api_client.task_channels.get_posts(channel_id, limit=limit)


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


async def get_battle_status(user_id: int) -> JsonDict:
    return await api_client.battles.get_status(user_id)


async def get_theft_status(user_id: int) -> JsonDict:
    return await api_client.thefts.get_status(user_id)


async def ingest_task_channel_post_via_api(
        *,
        chat_id: str,
        channel_post_id: int,
        title: Optional[str],
        reward: float = 0.01,
) -> JsonDict:
    return await api_client.tasks.ingest_channel_post(
        chat_id=chat_id,
        channel_post_id=channel_post_id,
        title=title,
        reward=reward,
    )


async def open_task(user_id: int, task_id: int) -> JsonDict:
    return await api_client.tasks.open(user_id, task_id)


async def check_task(user_id: int, task_id: int, *, session_id: Optional[str] = None) -> JsonDict:
    return await api_client.tasks.check(user_id, task_id, session_id=session_id)


async def report_task_unavailable(user_id: int, task_id: int, *, reason: Optional[str] = None) -> JsonDict:
    return await api_client.tasks.report_unavailable(user_id, task_id, reason=reason)


__all__ = [
    "ApiClientError",
    "BotApiClient",
    "api_client",
    "get_user_profile",
    "get_user_stats",
    "get_user_battle_stats",
    "get_user_theft_stats",
    "get_user_ledger_page",
    "get_user_risk_page",
    "lookup_user",
    "set_user_role",
    "adjust_user_balance",
    "mark_user_suspicious",
    "clear_user_suspicious",
    "list_campaigns_via_api",
    "get_campaign_via_api",
    "create_campaign_via_api",
    "set_campaign_status_via_api",
    "delete_campaign_via_api",
    "add_campaign_winners_via_api",
    "get_campaigns_summary_via_api",
    "get_campaign_stats_via_api",
    "get_campaign_winners_via_api",
    "delete_campaign_winner_via_api",
    "list_promos_via_api",
    "get_promo_via_api",
    "create_promo_via_api",
    "set_promo_status_via_api",
    "delete_promo_via_api",
    "get_promos_summary_via_api",
    "get_promo_stats_via_api",
    "get_top_balances_via_api",
    "get_growth_via_api",
    "get_admin_ledger_page_via_api",
    "get_audit_via_api",
    "list_withdrawals_queue",
    "get_withdrawal_details",
    "mark_withdrawal_paid",
    "reject_withdrawal",
    "list_recent_fee_payments_via_api",
    "record_withdrawal_fee_refund",
    "record_fee_refund_by_charge_id",
    "list_task_channels_via_api",
    "get_task_channel_via_api",
    "create_task_channel_via_api",
    "bind_task_channel_client_via_api",
    "toggle_task_channel_via_api",
    "update_task_channel_params_via_api",
    "get_task_channel_posts_via_api",
    "bootstrap_bot_user_via_api",
    "get_bot_main_menu_for_user_context_via_api",
    "get_bot_main_menu_via_api",
    "get_next_task",
    "get_theft_status",
    "get_battle_status",
    "ingest_task_channel_post_via_api",
    "open_task",
    "check_task",
    "report_task_unavailable",
]
