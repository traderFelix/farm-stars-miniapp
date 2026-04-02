import asyncio, logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from .api_client import ingest_task_channel_post_via_api
from .pending_channel_posts import TaskChannelPostPayload, flush_pending_task_channel_posts
from shared.config import TELEGRAM_BOT_TOKEN
from .handlers import user_router, admin_router, admin_fallback_router, errors_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("farm_stars.log"),
        logging.StreamHandler()
    ]
)

logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


async def _ingest_pending_task_channel_post(payload: TaskChannelPostPayload) -> None:
    await ingest_task_channel_post_via_api(
        chat_id=payload["chat_id"],
        channel_post_id=payload["channel_post_id"],
        title=payload["title"],
        reward=payload["reward"],
    )


async def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан.")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(user_router)
    dp.include_router(admin_router)
    dp.include_router(admin_fallback_router)
    dp.include_router(errors_router)

    flush_result = await flush_pending_task_channel_posts(
        _ingest_pending_task_channel_post,
        limit=500,
    )
    if flush_result["flushed"] > 0 or flush_result["remaining"] > 0:
        logging.getLogger(__name__).info(
            "Startup flush for pending task channel posts flushed=%s remaining=%s",
            flush_result["flushed"],
            flush_result["remaining"],
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
