# handlers/bot_handlers.py
from __future__ import annotations
import logging
from typing import Dict, Any, List

from telethon import events, types, TelegramClient
from telethon.events import NewMessage, CallbackQuery
from telethon.tl.types import User, Message
from config import settings
from services import user_service, utilites
from services.db import insert_many_from_exported, get_invites_by_owner, get_all_invites, upsert_user_basic

from decorators.auth import require_role, Role

from locales.kbrds import main_menu, links_inline_menu, back_to_links_btn
from locales.texts import get_text, get_all_btns_list, links_list_to_str

log = logging.getLogger("app")


# Простейшее хранилище состояний диалога (по user_id)
STATE: Dict[int, Dict[str, Any]] = {}

def private_only(func):
    async def wrapper(event, *args, **kwargs):
        if not event.is_private:
            return
        return await func(event, *args, **kwargs)
    return wrapper


def setup_bot_handlers(client: TelegramClient, user_client: TelegramClient) -> None:
    """
    Регистрирует хендлеры команд и меню.
    client      — Bot API клиент (бот)
    user_client — пользовательский клиент (юзербот с правами администратора канала)
    """

    # ---------------------- БАЗОВЫЕ КОМАНДЫ ----------------------

    @client.on(events.NewMessage(pattern=r"^/start$"))
    @private_only
    async def start(event: NewMessage) -> None:
        sender = await event.get_sender()
        if isinstance(sender, User):
            await upsert_user_basic(sender)

        await event.respond(get_text("START_TEXT"), buttons=main_menu())


    @client.on(events.NewMessage(pattern=r"^/menu$"))
    @private_only
    async def show_menu(event: NewMessage) -> None:
        await event.respond(get_text("MAIN_MENU_TEXT"), buttons=main_menu())

    # Демонстрационный хендлер доступа по ролям (оставлен из вашего примера)
    @client.on(events.NewMessage(pattern=r"^/super"))
    @private_only
    @require_role({Role.SUPER})
    async def super_only(event: NewMessage) -> None:
        # пример использования ранее написанной логики получения ссылок
        user_id = event.sender_id
        data = await get_all_invites()
        if data:
            file = await utilites.create_excel(data, owners=True)
            await client.send_file(entity=user_id, caption=get_text("TOTAL_STAT_TEXT"), file=file)
        else:
            await event.respond(get_text("NO_STAT_TEXT"))
        return

    # ---------------------- КНОПКА: СОЗДАНИЕ ССЫЛОК ----------------------
    # Поскольку тексты локализованы, проверяем raw_text против всех вариантов
    @client.on(events.NewMessage)
    @private_only
    @require_role({Role.SUPER, Role.BUYER})
    async def menu_buttons_router(event: NewMessage) -> None:
        text = (event.raw_text or "").strip()
        user_id = event.sender_id
        # Открыть инлайн-меню генерации ссылок
        if text in get_all_btns_list("BTN_CREATE_LINK"):
            await event.respond(get_text("CREATE_LINK_TEXT"), buttons=links_inline_menu())
            return
        
        # Открыть инлайн-меню генерации ссылок
        if text in get_all_btns_list("BTN_STAT"):
            # генерируем статистику по всем ссылкам юзера в файл ексель и отправляем
            data = await get_invites_by_owner(user_id)
            if data:
                file = await utilites.create_excel(data)
                await client.send_file(entity=user_id, caption=get_text("YOUR_STAT_TEXT"), file=file)
            else:
                await event.respond(get_text("NO_STAT_TEXT"))
            return

        # Остальные сообщения обработаем в "шаговом" диалоге (ниже),
        # если есть активное состояние. Иначе выходим.
        st = STATE.get(user_id)
        if not st:
            return

        # ---------- Шаги диалога после нажатия инлайн-кнопок ----------
        mode: str = st.get("mode")
        step: str = st.get("step")

        # 1) Режим: без названия — спрашиваем количество
        if mode == "no_title" and step == "ask_count":
            try:
                n = int(text)
            except ValueError:
                await event.reply(get_text("ASK_COUNT"))
                return
            if not (1 <= n <= 50):
                await event.reply(get_text("ASK_COUNT"))
                return
            prompt: Message = STATE.get(user_id, {}).get("prompt_msg")
            if prompt:
                try:
                    await prompt.delete()
                except Exception:
                    pass
            # стало:
            status = await event.respond(get_text('CREATING_LINKS'))
            try:
                links: List[types.ChatInviteExported] = await user_service.create_links_no_title(
                    user_client,
                    settings.target_chat_id,
                    n
                )
                await insert_many_from_exported(links, settings.target_chat_id, user_id)
                STATE.pop(user_id, None)
                await event.reply(links_list_to_str(links), buttons=main_menu())
                await status.edit(f"{get_text('READY_LINKS')}")

            except Exception as e:
                log.exception("create_links_no_title")
                await status.edit(f"{get_text('CREATING_LINKS_ERROR')}: {e}")
                STATE.pop(user_id, None)
            return

        # 2) Режим: по списку названий
        if mode == "titles" and step == "ask_list":
            titles = [line.strip() for line in text.splitlines() if line.strip()]
            if not titles:
                await event.reply(get_text("ASK_TITLES"))
                return
            if len(titles) > 50:
                await event.reply(get_text("ASK_TITLES"))
                return
            # стало:
            prompt: Message = STATE.get(user_id, {}).get("prompt_msg")
            if prompt:
                try:
                    await prompt.delete()
                except Exception:
                    pass
            status = await event.respond(get_text('CREATING_LINKS'))
            try:
                links: List[types.ChatInviteExported] = await user_service.create_links_with_titles(
                    user_client,
                    settings.target_chat_id,
                    titles
                )
                await insert_many_from_exported(links, settings.target_chat_id, user_id)
                STATE.pop(user_id, None)
                await event.reply(links_list_to_str(links), buttons=main_menu())
                await status.edit(f"{get_text('READY_LINKS')}")
            except Exception as e:
                log.exception("create_links_with_titles")
                await status.edit(f"{get_text('CREATING_LINKS_ERROR')}: {e}")
                STATE.pop(user_id, None)
            return

        # 3) Режим: по маске
        if mode == "mask":
            if step == "ask_mask":
                if not text:
                    await event.reply(get_text("ASK_MASK"))
                    return
                st["mask"] = text
                st["step"] = "ask_count"
                ask_msg = await event.reply(get_text("ASK_COUNT"), buttons=back_to_links_btn())
                prompt: Message = STATE.get(user_id, {}).get("prompt_msg")
                if prompt:
                    try:
                        await prompt.delete()
                    except Exception:
                        pass
                st["prompt_msg"] = ask_msg  # теперь удалим именно это сообщение перед генерацией
                return

            if step == "ask_count":
                try:
                    n = int(text)
                except ValueError:
                    await event.reply(get_text("ASK_COUNT"))
                    return
                if not (1 <= n <= 50):
                    await event.reply(get_text("ASK_COUNT"))
                    return

                mask: str = st.get("mask", "")
                prompt: Message = STATE.get(user_id, {}).get("prompt_msg")
                if prompt:
                    try:
                        await prompt.delete()
                    except Exception:
                        pass
                status = await event.respond(get_text('CREATING_LINKS'))
                try:
                    links: List[types.ChatInviteExported] = await user_service.create_links_with_mask(
                        user_client,
                        settings.target_chat_id,
                        mask,
                        n
                    )
                    await insert_many_from_exported(links, settings.target_chat_id, user_id)
                    STATE.pop(user_id, None)
                    await event.reply(links_list_to_str(links), buttons=main_menu())
                    await status.edit(f"{get_text('READY_LINKS')}")
                except Exception as e:
                    log.exception("create_links_with_mask")
                    await status.edit(f"{get_text('CREATING_LINKS_ERROR')}: {e}")
                    STATE.pop(user_id, None)
                return

    # ---------------------- ИНЛАЙН-КНОПКИ: ВЫБОР РЕЖИМА ----------------------

    @client.on(events.CallbackQuery(pattern=b"gen:no_title"))
    @private_only
    @require_role({Role.SUPER, Role.BUYER})
    async def cb_no_title(event: CallbackQuery) -> None:
        msg = await event.edit(get_text("ASK_COUNT"), buttons=back_to_links_btn())
        STATE[event.sender_id] = {"mode": "no_title", "step": "ask_count", "prompt_msg": msg}

    @client.on(events.CallbackQuery(pattern=b"gen:titles"))
    @private_only
    @require_role({Role.SUPER, Role.BUYER})
    async def cb_titles(event: CallbackQuery) -> None:
        msg = await event.edit(get_text("ASK_TITLES"), buttons=back_to_links_btn())
        STATE[event.sender_id] = {"mode": "titles", "step": "ask_list", "prompt_msg": msg}

    @client.on(events.CallbackQuery(pattern=b"gen:mask"))
    @private_only
    @require_role({Role.SUPER, Role.BUYER})
    async def cb_mask(event: CallbackQuery) -> None:
        
        msg = await event.edit(get_text("ASK_MASK"), buttons=back_to_links_btn())
        STATE[event.sender_id] = {"mode": "mask", "step": "ask_mask", "prompt_msg": msg}

    @client.on(events.CallbackQuery(pattern=b"gen:cancel"))
    @private_only
    async def cb_cancel(event: CallbackQuery) -> None:
        STATE.pop(event.sender_id, None)
        await event.edit(get_text("MAIN_MENU_TEXT"))
    

    @client.on(events.CallbackQuery(pattern=b"gen:back"))
    @private_only
    async def cb_cancel(event: CallbackQuery) -> None:
        STATE.pop(event.sender_id, None)
        await event.edit(get_text("CREATE_LINK_TEXT"), buttons=links_inline_menu())
