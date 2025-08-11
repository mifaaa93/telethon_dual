import asyncio
import logging
from pathlib import Path
import signal
from telethon import TelegramClient
from config import settings
from handlers.bot_handlers import setup_bot_handlers
from services.db import init_db, close_db
from services.scheduler import sync_invites_job
import contextlib



def setup_logging(level: str, log_file: str | None = None) -> None:
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file:
        # создаём папку, если надо
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handlers,
    )


async def run():
    settings.validate()
    setup_logging(settings.log_level, log_file="logs/app.log")
    log = logging.getLogger("app")

    # нужно вызвать init_db()
    await init_db()
    # Юзербот (аккаунт)
    user_client = TelegramClient(settings.user_session, settings.api_id, settings.api_hash)

    # Обычный бот (Bot API)
    bot_client = TelegramClient(settings.bot_session, settings.api_id, settings.api_hash)
    bot_client.parse_mode = 'html'  # короткая запись
    setup_bot_handlers(bot_client, user_client)

    # Старт клиентов
    await user_client.start(phone=settings.user_phone, password=settings.user_pass)  # При первом запуске запросит код/2FA в консоли
    await bot_client.start(bot_token=settings.bot_token)

    log.info("Both clients started: userbot + bot")

    # Грейсфул-шатдаун
    stop_event = asyncio.Event()

    def _ask_exit(signame):
        log.warning("Got signal %s: shutting down...", signame)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _ask_exit, s.name)
        except NotImplementedError:
            # Windows
            pass
    # Можно вынести период в settings.sync_interval_sec (секунды)
    sync_interval = getattr(settings, "sync_interval_sec", 300)
    include_revoked = getattr(settings, "sync_include_revoked", False)

    scheduler_task = asyncio.create_task(
        sync_invites_job(
            user_client=user_client,
            chat_id=settings.target_chat_id,
            interval_sec=sync_interval,
            stop_event=stop_event,
            include_revoked=include_revoked,
        ),
        name="sync_invites_job",
    )

    # Параллельная работа двух клиентов
    async def wait_disconnected():
        await asyncio.gather(
            bot_client.run_until_disconnected(),
            stop_event.wait(),
        )

    try:
        await wait_disconnected()
    finally:
        log.info("Disconnecting clients...")
        scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler_task
        await asyncio.gather(
            user_client.disconnect(),
            bot_client.disconnect(),
            close_db(),
            return_exceptions=True,
        )
        log.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(run())