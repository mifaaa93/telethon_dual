# services/scheduler.py
from __future__ import annotations
import asyncio
import logging
from typing import Optional
from telethon import TelegramClient

from services import user_service
from services.db import insert_many_from_exported  # если у тебя другой апдейтер — замени здесь

async def sync_invites_job(
    user_client: TelegramClient,
    chat_id: int | str,
    interval_sec: int = 300,            # период опроса (сек)
    stop_event: Optional[asyncio.Event] = None,
    include_revoked: bool = False,      # нужно ли подтягивать отозванные
) -> None:
    """
    Периодически обновляет в БД статистику по пригласительным ссылкам канала.
    Завершается, когда stop_event установлен или задача отменена.
    """
    log = logging.getLogger("app")
    log.info(f"[scheduler] старт: interval={interval_sec}s, chat_id={chat_id}, include_revoked={include_revoked}")

    # локальная обёртка ожидания, чтобы можно было выйти раньше, если пришёл stop_event
    async def _sleep_or_stop(seconds: float) -> bool:
        if stop_event is None:
            await asyncio.sleep(seconds)
            return False
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    while True:
        # выход по сигналу остановки
        if stop_event and stop_event.is_set():
            log.info("[scheduler] stop_event set — выходим")
            break

        try:
            links = await user_service.get_all_links(
                user_client,
                chat_id,
                include_revoked=include_revoked,
                delay_sec=0.6,   # мягкий рейтлимит между страницами
                jitter_sec=0.3,
            )
            count = len(links)
            log.info(f"[scheduler] получено ссылок: {count}")

            # Сохраняем/обновляем в БД
            # insert_many_from_exported — твоя функция; предполагаем, что она делает upsert.
            await insert_many_from_exported(links, chat_id, owner_tg_id=None)
            log.info("[scheduler] сохранение в БД завершено")

        except asyncio.CancelledError:
            log.info("[scheduler] задача отменена")
            break
        except Exception as e:
            log.exception(f"[scheduler] ошибка при синхронизации: {e}")

        # ждём следующий цикл или выходим, если пришёл сигнал
        should_stop = await _sleep_or_stop(interval_sec)
        if should_stop:
            log.info("[scheduler] остановлено во время ожидания")
            break

    log.info("[scheduler] завершено")
