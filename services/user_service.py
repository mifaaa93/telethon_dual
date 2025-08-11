# services/user_service.py
from __future__ import annotations
import asyncio, random, logging
import datetime as dt
from typing import Optional, Iterable, List, Callable, TypeVar
from telethon import TelegramClient
from telethon.tl import functions, types
from telethon.errors import FloodWaitError, RpcCallFailError

T = TypeVar("T")
# Логгер общий для всего приложения
log = logging.getLogger("app")

# --------- Общие helpers: задержка и повтор при FLOOD ---------

async def _sleep_delay(base: float, jitter: float) -> None:
    if base > 0:
        delay = base + (random.random() * max(0.0, jitter))
        log.debug(f"Пауза {delay:.2f} сек между запросами")
        await asyncio.sleep(delay)

async def _with_flood_retry(
    coro_factory: Callable[[], "asyncio.Future[T]"],
    *,
    max_retries: int = 5,
    flood_extra_sec: int = 1,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> T:
    """
    Безопасно выполняет Telethon-запрос:
    - ловит FloodWaitError и ждёт e.seconds + flood_extra_sec
    - повторяет до max_retries (для FloodWaitError — без ограничения)
    - логирует все ожидания
    """
    attempt = 0
    while True:
        try:
            return await coro_factory()
        except FloodWaitError as e:
            attempt += 1
            wait_time = e.seconds + flood_extra_sec
            log.warning(f"[FloodWait] Попытка #{attempt}: ждём {wait_time} сек перед повтором")
            if on_retry:
                on_retry(attempt, e)
            await asyncio.sleep(wait_time)
            continue
        except RpcCallFailError as e:
            attempt += 1
            if attempt > max_retries:
                log.error(f"[RPC Error] Превышено число повторов ({max_retries}), ошибка: {e}")
                raise
            backoff = min(2 ** attempt, 8)
            log.warning(f"[RPC Error] Попытка #{attempt}: ждём {backoff} сек перед повтором. Ошибка: {e}")
            if on_retry:
                on_retry(attempt, e)
            await asyncio.sleep(backoff)
            continue


# --------- Создание одной ссылки ---------

async def create_invite_link(
    client: TelegramClient,
    target_chat: int | str,
    *,
    title: Optional[str] = None,
    expire_at: Optional[dt.datetime] = None,
    expire_in: Optional[dt.timedelta] = None,
    usage_limit: Optional[int] = None,
    request_needed: bool = False,
) -> types.ChatInviteExported:
    expire_date: Optional[int] = None
    if expire_at:
        expire_date = int((expire_at if expire_at.tzinfo else expire_at.replace(tzinfo=dt.timezone.utc))
                          .astimezone(dt.timezone.utc).timestamp())
    elif expire_in:
        expire_date = int((dt.datetime.now(dt.timezone.utc) + expire_in).timestamp())
    if usage_limit is not None and usage_limit <= 0:
        usage_limit = None

    def _do():
        return client(functions.messages.ExportChatInviteRequest(
            peer=target_chat,
            title=(title[:32] if title else None),
            expire_date=expire_date,
            usage_limit=usage_limit,
            request_needed=request_needed,
        ))

    return await _with_flood_retry(_do)

# --------- Батчи с равномерной задержкой между успешными запросами ---------

async def create_links_no_title(
            client: TelegramClient,
            target_chat: int | str,
            count: int,
            *,
            delay_sec: float = 0.3,
            jitter_sec: float = 0.2,
        ) -> List[types.ChatInviteExported]:
    count = max(1, min(100, count))
    out: List[types.ChatInviteExported] = []
    ts = dt.datetime.now().strftime("%m%d%H%M")
    for i in range(1, count + 1):
        title = f"Link {ts}-{i}"
        inv = await create_invite_link(client, target_chat, title=title)
        out.append(inv)
        # задержка только ПОСЛЕ успешного запроса (межстраничный рейтлимит)
        await _sleep_delay(delay_sec, jitter_sec)
    return out

async def create_links_with_titles(
            client: TelegramClient,
            target_chat: int | str,
            titles: Iterable[str],
            *,
            delay_sec: float = 0.3,
            jitter_sec: float = 0.2,
        ) -> List[types.ChatInviteExported]:
    out: List[types.ChatInviteExported] = []
    for raw in titles:
        t = (raw or "").strip()
        inv = await create_invite_link(client, target_chat, title=(t[:32] if t else None))
        out.append(inv)
        await _sleep_delay(delay_sec, jitter_sec)
    return out

async def create_links_with_mask(
            client: TelegramClient,
            target_chat: int | str,
            mask: str,
            count: int,
            *,
            delay_sec: float = 0.3,
            jitter_sec: float = 0.2,
        ) -> List[types.ChatInviteExported]:
    count = max(1, min(100, count))
    mask = (mask or "").strip()
    out: List[types.ChatInviteExported] = []
    for i in range(1, count + 1):
        title = mask.replace("{n}", str(i)) if "{n}" in mask else f"{mask} {i}".strip()
        inv = await create_invite_link(client, target_chat, title=(title[:32] if title else None))
        out.append(inv)
        await _sleep_delay(delay_sec, jitter_sec)
    return out


async def get_all_links(
            client: TelegramClient,
            target_chat: int | str,
            *,
            include_revoked: bool = False,
            delay_sec: float = 0.3,
            jitter_sec: float = 0.2,
            page_limit: int = 100,
        ) -> List[types.ChatInviteExported]:
    me = await client.get_me()
    invites: List[types.ChatInviteExported] = []

    async def _fetch_page(offset_date: Optional[dt.datetime], offset_link: Optional[str], revoked: bool):
        return await _with_flood_retry(lambda: client(functions.messages.GetExportedChatInvitesRequest(
            peer=target_chat,
            admin_id=me,
            limit=page_limit,
            offset_date=offset_date,
            offset_link=offset_link,
            revoked=revoked,
        )))

    async def collect(revoked: bool):
        offset_date: Optional[dt.datetime] = None
        offset_link: Optional[str] = None
        while True:
            res: types.messages.ExportedChatInvites = await _fetch_page(offset_date, offset_link, revoked)
            if not res.invites:
                break
            invites.extend(res.invites)
            last = res.invites[-1]
            next_date = getattr(last, "date", None)
            next_link = getattr(last, "link", None)
            if not next_date or not next_link:
                break
            offset_date, offset_link = next_date, next_link
            if len(res.invites) < page_limit:
                break
            await _sleep_delay(delay_sec, jitter_sec)

    await collect(False)
    if include_revoked:
        await collect(True)
    return invites
