import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    opencode_server_url: str = field(default_factory=lambda: os.getenv("OPENCODE_SERVER_URL", "http://127.0.0.1:4096"))
    opencode_working_dir: str = field(default_factory=lambda: os.getenv("OPENCODE_WORKING_DIR", ""))
    bridger_timeout: int = field(default_factory=lambda: int(os.getenv("BRIDGER_TIMEOUT", "300")))
    bridger_log_level: str = field(default_factory=lambda: os.getenv("BRIDGER_LOG_LEVEL", "INFO"))

    def __post_init__(self):
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not self.telegram_chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is required")
        if not self.opencode_working_dir:
            raise ValueError("OPENCODE_WORKING_DIR is required")

def load_config() -> Config:
    return Config()