# handlers/bot_handlers.py
from __future__ import annotations
import logging
from typing import Dict, Any, List, Callable, Awaitable

from telethon import events, types, TelegramClient
from telethon.events import NewMessage, CallbackQuery
from telethon.tl.types import User, Message
from config import settings
from services import user_service, utilites
from services.db import insert_many_from_exported, get_invites_by_owner, get_all_invites, upsert_user_basic

from decorators.auth import require_role, Role

from locales.kbrds import main_menu, links_inline_menu, back_to_links_btn, stat_inline_menu, back_to_stat_btn
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


async def _create_and_send_links(
                client: TelegramClient,
                user_client: TelegramClient,
                user_id: int,
                prompt_msg: Message | None,
                create_coro_factory: Callable[[], Awaitable[List[types.ChatInviteExported]]],
                ) -> None:
    """
    Удаляет предыдущее бот-сообщение с кнопкой «Назад», показывает статус,
    создаёт ссылки, сохраняет в БД и отправляет результат одним местом.
    """
    # 1) снести предыдущее "вопрос/назад"
    if prompt_msg:
        try:
            await prompt_msg.delete()
        except Exception:
            pass

    # 2) статус
    status = await client.send_message(user_id, get_text('CREATING_LINKS'))

    try:
        # 3) создать ссылки
        links = await create_coro_factory()

        # 4) сохранить в БД
        await insert_many_from_exported(links, settings.target_chat_id, user_id)

        # 5) ответ с результатом
        try:
            to_answer = await client.send_message(user_id, links_list_to_str(links), buttons=main_menu())
        except Exception as e:
            to_answer = None
        if links:
            file = await utilites.create_excel_from_(links)
            await client.send_file(entity=user_id, file=file, reply_to=to_answer, buttons=main_menu())
        # 6) обновить статус
        await status.edit(get_text('READY_LINKS'))

    except Exception as e:
        log.exception("links_creation_failed")
        try:
            await status.edit(f"{get_text('CREATING_LINKS_ERROR')}: {e}")
        except Exception:
            pass
    finally:
        STATE.pop(user_id, None)



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
        
        # Открыть инлайн-меню статистики
        if text in get_all_btns_list("BTN_STAT"):
            await event.respond(get_text("MAIN_STAT_TEXT"), buttons=stat_inline_menu())
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
            await _create_and_send_links(
                client,
                user_client,
                user_id,
                prompt,
                create_coro_factory=lambda: user_service.create_links_no_title(
                    user_client, settings.target_chat_id, n
                ),
            )
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
            await _create_and_send_links(
                    client,
                    user_client,
                    user_id,
                    prompt,
                    create_coro_factory=lambda: user_service.create_links_with_titles(
                        user_client, settings.target_chat_id, titles
                    ),
                )
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
                await _create_and_send_links(
                    client,
                    user_client,
                    user_id,
                    prompt,
                    create_coro_factory=lambda: user_service.create_links_with_mask(
                        user_client, settings.target_chat_id, mask, n
                    ),
                )
                return
        # 4) Режим: статистика по списку ссылок
        if mode == "stat" and step == "ask_links":
            links = [line.strip() for line in text.splitlines() if line.strip()]
            if not links:
                await event.reply(get_text("ASK_STAT_LINKS"))
                return
            # стало:
            prompt: Message = STATE.get(user_id, {}).get("prompt_msg")
            STATE.pop(user_id, None)
            if prompt:
                try:
                    prompt.delete()
                except Exception as e:
                    log.error(f"prompt.delete(): {e}")
            data = await get_invites_by_owner(user_id)
            if data:
                file = await utilites.create_excel(data, include=links)
                await client.send_file(entity=user_id, caption=get_text("YOUR_STAT_TEXT"), file=file, buttons=main_menu())
            else:
                await event.respond(get_text("NO_STAT_TEXT"))
            
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

    @client.on(events.CallbackQuery(pattern=b"(gen|stat):cancel"))
    @private_only
    async def cb_cancel(event: CallbackQuery) -> None:
        STATE.pop(event.sender_id, None)
        await event.edit(get_text("MAIN_MENU_TEXT"))
    

    @client.on(events.CallbackQuery(pattern=b"gen:back"))
    @private_only
    async def cb_back(event: CallbackQuery) -> None:
        STATE.pop(event.sender_id, None)
        await event.edit(get_text("CREATE_LINK_TEXT"), buttons=links_inline_menu())
    

    @client.on(events.CallbackQuery(pattern=b"stat:back"))
    @private_only
    async def stat_back(event: CallbackQuery) -> None:
        STATE.pop(event.sender_id, None)
        await event.edit(get_text("MAIN_STAT_TEXT"), buttons=stat_inline_menu())
    

    @client.on(events.CallbackQuery(pattern=b"stat:all"))
    @private_only
    async def stat_all_btn(event: CallbackQuery) -> None:

        user_id = event.sender_id
        data = await get_invites_by_owner(user_id)
        if data:
            file = await utilites.create_excel(data)
            await client.send_file(entity=user_id, caption=get_text("YOUR_STAT_TEXT"), file=file, buttons=main_menu())
        else:
            await event.respond(get_text("NO_STAT_TEXT"))
        await event.answer()
        return
    
    @client.on(events.CallbackQuery(pattern=b"stat:links"))
    @private_only
    async def stat_links_btn(event: CallbackQuery) -> None:

        msg = await event.edit(get_text("ASK_STAT_LINKS"), buttons=back_to_stat_btn())
        STATE[event.sender_id] = {"mode": "stat", "step": "ask_links", "prompt_msg": msg}

