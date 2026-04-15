import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional, TypedDict

from shared.config import BOT_TASK_CHANNEL_POST_QUEUE_PATH

logger = logging.getLogger(__name__)


class TaskChannelPostPayload(TypedDict):
    chat_id: str
    channel_post_id: int
    title: Optional[str]
    reward: float


TaskChannelPostIngestCallback = Callable[[TaskChannelPostPayload], Awaitable[object]]


def build_task_channel_post_payload(
        *,
        chat_id: str,
        channel_post_id: int,
        title: Optional[str],
        reward: float = 0.01,
) -> TaskChannelPostPayload:
    return {
        "chat_id": str(chat_id),
        "channel_post_id": int(channel_post_id),
        "title": title,
        "reward": float(reward),
    }


def _queue_path() -> Path:
    return Path(BOT_TASK_CHANNEL_POST_QUEUE_PATH)


def _same_channel_post(
        left: TaskChannelPostPayload,
        right: TaskChannelPostPayload,
) -> bool:
    return (
        str(left["chat_id"]) == str(right["chat_id"])
        and int(left["channel_post_id"]) == int(right["channel_post_id"])
    )


def _normalize_payload(raw_payload: dict) -> TaskChannelPostPayload:
    title = raw_payload.get("title")
    if title is not None and not isinstance(title, str):
        title = str(title)

    return build_task_channel_post_payload(
        chat_id=str(raw_payload["chat_id"]),
        channel_post_id=int(raw_payload["channel_post_id"]),
        title=title,
        reward=float(raw_payload.get("reward") or 0.01),
    )


def _load_pending_task_channel_posts() -> list[TaskChannelPostPayload]:
    path = _queue_path()
    if not path.exists():
        return []

    items: list[TaskChannelPostPayload] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue

        try:
            raw_payload = json.loads(raw_line)
            if not isinstance(raw_payload, dict):
                raise ValueError("queue item must be a JSON object")
            items.append(_normalize_payload(raw_payload))
        except Exception:
            logger.warning(
                "Skipping invalid pending task channel post queue item path=%s line=%s",
                path,
                line_number,
                exc_info=True,
            )

    return items


def _write_pending_task_channel_posts(items: list[TaskChannelPostPayload]) -> None:
    path = _queue_path()

    if not items:
        if path.exists():
            path.unlink()
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for item in items:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def enqueue_task_channel_post_for_retry(payload: TaskChannelPostPayload) -> int:
    items = _load_pending_task_channel_posts()

    for index, existing in enumerate(items):
        if _same_channel_post(existing, payload):
            items[index] = payload
            _write_pending_task_channel_posts(items)
            return len(items)

    items.append(payload)
    _write_pending_task_channel_posts(items)
    return len(items)


async def flush_pending_task_channel_posts(
        ingest_callback: TaskChannelPostIngestCallback,
        *,
        limit: int = 100,
) -> dict[str, int]:
    items = _load_pending_task_channel_posts()
    if not items:
        return {"flushed": 0, "remaining": 0}

    flushed = 0
    remaining: list[TaskChannelPostPayload] = []

    for index, item in enumerate(items):
        if flushed >= limit:
            remaining.extend(items[index:])
            break

        try:
            await ingest_callback(item)
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc)
            if exc.__class__.__name__ == "ApiClientError":
                logger.warning(
                    "Failed to flush pending task channel post chat_id=%s post_id=%s detail=%s",
                    item["chat_id"],
                    item["channel_post_id"],
                    detail,
                )
            else:
                logger.warning(
                    "Failed to flush pending task channel post chat_id=%s post_id=%s detail=%s",
                    item["chat_id"],
                    item["channel_post_id"],
                    detail,
                    exc_info=True,
                )
            remaining.append(item)
            remaining.extend(items[index + 1:])
            break

        flushed += 1

    _write_pending_task_channel_posts(remaining)
    return {"flushed": flushed, "remaining": len(remaining)}
