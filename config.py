from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

def _parse_int_list(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(x) for x in value.split(',') if x]


@dataclass
class Settings:
    
    admins_super: list[int] = None  # type: ignore
    admins_buyer: list[int] = None  # type: ignore
    admins_other: list[int] = None  # type: ignore
    target_chat_id = int(os.getenv("TARGET_CHAT_ID"))
    api_id: int = int(os.getenv("API_ID", "0"))
    api_hash: str = os.getenv("API_HASH", "")
    user_session: str = os.getenv("USER_SESSION", "user.session")
    bot_session: str = os.getenv("BOT_SESSION", "bot.session")
    user_phone: str = os.getenv("USER_PHONE", "")
    user_pass: str = os.getenv("USER_PASS", None)
    bot_token: str = os.getenv("BOT_TOKEN", "")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    db_path: str = os.getenv("DB_PATH", "db.sqlite")
    sync_interval_sec: int = int(os.getenv("SYNC_INTERVAL", "300"))
    sync_include_revoked: bool = False
    
    def __post_init__(self) -> None:
        self.admins_super = _parse_int_list(os.getenv("ADMINS_SUPER"))
        self.admins_buyer = _parse_int_list(os.getenv("ADMINS_BUYER"))
        self.admins_other = _parse_int_list(os.getenv("ADMINS_OTHER"))

    def validate(self) -> None:
        missing = []
        if not self.api_id:
            missing.append("API_ID")
        if not self.api_hash:
            missing.append("API_HASH")
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if not self.user_phone:
            missing.append("USER_PHONE")
        if missing:
            raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

settings = Settings()