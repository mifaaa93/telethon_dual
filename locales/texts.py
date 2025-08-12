from typing import List
from telethon import types
from html import escape

texts_dict = {
    "START_TEXT": {
        "RU": "Привет! Выберите действие из меню:"
    },
    "MAIN_MENU_TEXT": {
        "RU": "Меню:"
    },
    "CANCELED_TEXT": {  # было CANCALED_TEXT
        "RU": "Ок, отменено."
    },
    "CREATE_LINK_TEXT": {
        "RU": "Выберите способ генерации ссылок:"
    },
    "ASK_COUNT": {
        "RU": "Укажите количество (1-50):"
    },
    "ASK_TITLES": {
        "RU": "Пришлите названия в столбик (каждая строка — отдельная ссылка, максимум 50):"
    },
    "ASK_MASK": {
        "RU": "Укажите маску (шаблон) названия. Поддерживается {n}. Если {n} не указано — добавим номер в конец."
    },
    "READY_LINKS": {
        "RU": "✅ Ваши ссылки готовы"
    },
    "CREATING_LINKS": {
        "RU": "⏳ Создаю ссылки... это может занять несколько секунд"
    },
    "CREATING_LINKS_ERROR": {
        "RU": "⚠️ Не удалось создать ссылки: "
    },
    "YOUR_STAT_TEXT": {
        "RU": "Статистика по вашим ссылкам: "
    },
    "TOTAL_STAT_TEXT": {
        "RU": "Статистика по Всем ссылкам"
    },
    "MAIN_STAT_TEXT": {
        "RU": "Какой тип статистики по ссылкам:"
    },
    "NO_STAT_TEXT": {
        "RU": "У вас нет ссылок!"
    },
    "NO_ACCESS_TEXT": {
        "RU": "⛔ У вас нет доступа к этой команде."
    },
    "ASK_STAT_LINKS": {
        "RU": "Напишите список ссылок для статистики (каждая ссылка с новой строки)"
    },
    
}

btns_dict = {
    "BTN_CREATE_LINK": {
        "RU": "Создание ссылок"
    },
    "BTN_STAT": {
        "RU": "Статистика"
    },
    "BTN_CREATE_LINK_NO_TITLE": {
        "RU": "Без названия"
    },
    "BTN_CREATE_LINK_TITLES": {
        "RU": "По названиям"
    },
    "BTN_CREATE_LINK_MASK": {
        "RU": "По шаблону"
    },
    "BTN_CANCEL": {
        "RU": "Отмена"
    },
    "BTN_BACK_MAIN": {
        "RU": "⬅️ В главное меню"
    },
    "BTN_BACK": {
        "RU": "⬅️ Назад"
    },
    "BTN_STAT_ALL": {
        "RU": "По всем ссылкам"
    },
    "BTN_STAT_LINKS": {
        "RU": "По списку ссылок"
    },
}

def get_text(key: str, lang: str = "RU") -> str:
    if key in texts_dict:
        return texts_dict[key].get(lang) or texts_dict[key].get("RU", key)
    return key

def get_btn_text(key: str, lang: str = "RU") -> str:
    if key in btns_dict:
        return btns_dict[key].get(lang) or btns_dict[key].get("RU", key)
    return key


def get_all_btns_list(key: str) -> list:
    '''
    '''
    res = [key]
    if key in btns_dict:
        res += list(btns_dict.get(key).values())
    
    return res


def links_list_to_str(links: List[types.ChatInviteExported], lang: str = "RU") -> str:
    '''
    '''
    return "\n".join(f"<code>{escape(l.link)}</code> {escape(l.title or '')}" for l in links)
