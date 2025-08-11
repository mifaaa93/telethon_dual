from __future__ import annotations
from enum import Enum, auto
from typing import Callable, Iterable, Awaitable
from telethon.events.newmessage import NewMessage
from config import settings


class Role(Enum):
    SUPER = auto()
    BUYER = auto()
    OTHER = auto()


# Роль -> множество user_id
ROLE_MAP: dict[Role, set[int]] = {
    Role.SUPER: set(settings.admins_super),
    Role.BUYER: set(settings.admins_buyer),
    Role.OTHER: set(settings.admins_other),
}


def _user_roles(user_id: int | None) -> set[Role]:
    roles: set[Role] = set()
    if user_id is None:
        return roles
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            roles.add(role)
    return roles


def require_role(
    allowed: Iterable[Role],
) -> Callable[[Callable[[NewMessage.Event], Awaitable[None]]], Callable[[NewMessage.Event], Awaitable[None]]]:
    allowed_set = set(allowed)

    def decorator(handler: Callable[[NewMessage.Event], Awaitable[None]]):
        async def wrapper(event: NewMessage.Event) -> None:
            uid = event.sender_id  # type: ignore[attr-defined]
            roles = _user_roles(uid)
            if not roles.intersection(allowed_set):
                await event.reply("⛔ У вас нет доступа к этой команде.")
                return
            await handler(event)
        return wrapper

    return decorator
