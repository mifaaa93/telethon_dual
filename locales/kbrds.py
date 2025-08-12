# locales/kbrds.py
from telethon import types
from typing import Any
from locales.texts import get_btn_text

def main_menu(user: Any = None) -> types.ReplyKeyboardMarkup:
    """
    Компактное меню с resize=True.
    ВАЖНО: rows -> list[KeyboardButtonRow], а не list[list].
    """
    rows = [
        types.KeyboardButtonRow(buttons=[
            types.KeyboardButton(get_btn_text("BTN_CREATE_LINK")),
            types.KeyboardButton(get_btn_text("BTN_STAT")),
        ]),
        # Добавить ещё ряд — просто раскомментируй:
        # types.KeyboardButtonRow(buttons=[
        #     types.KeyboardButton(get_btn_text("BTN_SETTINGS")),
        #     types.KeyboardButton(get_btn_text("BTN_HELP")),
        # ]),
    ]
    return types.ReplyKeyboardMarkup(rows=rows, resize=True)

def links_inline_menu(user: Any = None) -> types.ReplyInlineMarkup:
    """
    Инлайн-клавиатура через TL-типы:
    - ReplyInlineMarkup
    - KeyboardButtonRow
    - KeyboardButtonCallback (callback_data — bytes)
    """
    rows = [
        types.KeyboardButtonRow(buttons=[
            types.KeyboardButtonCallback(
                text=get_btn_text("BTN_CREATE_LINK_NO_TITLE"),
                data=b"gen:no_title"
            )
        ]),
        types.KeyboardButtonRow(buttons=[
            types.KeyboardButtonCallback(
                text=get_btn_text("BTN_CREATE_LINK_TITLES"),
                data=b"gen:titles"
            )
        ]),
        types.KeyboardButtonRow(buttons=[
            types.KeyboardButtonCallback(
                text=get_btn_text("BTN_CREATE_LINK_MASK"),
                data=b"gen:mask"
            )
        ]),
        types.KeyboardButtonRow(buttons=[
            types.KeyboardButtonCallback(
                text=get_btn_text("BTN_CANCEL"),
                data=b"gen:cancel"
            )
        ]),
    ]
    return types.ReplyInlineMarkup(rows=rows)


def back_to_links_btn(user: Any = None) -> types.ReplyInlineMarkup:
    """
    """
    rows = [
        types.KeyboardButtonRow(buttons=[
            types.KeyboardButtonCallback(
                text=get_btn_text("BTN_BACK"),
                data=b"gen:back"
            )
        ]),
    ]
    return types.ReplyInlineMarkup(rows=rows)

def back_to_stat_btn(user: Any = None) -> types.ReplyInlineMarkup:
    """
    """
    rows = [
        types.KeyboardButtonRow(buttons=[
            types.KeyboardButtonCallback(
                text=get_btn_text("BTN_BACK"),
                data=b"stat:back"
            )
        ]),
    ]
    return types.ReplyInlineMarkup(rows=rows)


def stat_inline_menu(user: Any = None) -> types.ReplyInlineMarkup:
    """
    Инлайн-клавиатура через TL-типы:
    - ReplyInlineMarkup
    - KeyboardButtonRow
    - KeyboardButtonCallback (callback_data — bytes)
    """
    rows = [

        types.KeyboardButtonRow(buttons=[
            types.KeyboardButtonCallback(
                text=get_btn_text("BTN_STAT_LINKS"),
                data=b"stat:links"
            )
        ]),
        types.KeyboardButtonRow(buttons=[
            types.KeyboardButtonCallback(
                text=get_btn_text("BTN_STAT_ALL"),
                data=b"stat:all"
            )
        ]),
        types.KeyboardButtonRow(buttons=[
            types.KeyboardButtonCallback(
                text=get_btn_text("BTN_CANCEL"),
                data=b"stat:cancel"
            )
        ]),
    ]
    return types.ReplyInlineMarkup(rows=rows)