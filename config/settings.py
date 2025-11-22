"""
Глобальные настройки PBN Manager
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Базовые пути
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Создаём директории если не существуют
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# База данных
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/pbn_manager.db")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
DALLE_MODEL = os.getenv("DALLE_MODEL", "dall-e-3")

# Шифрование credentials
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")  # Fernet key для шифрования паролей

# Прокси (глобальные, могут быть переопределены для каждого сайта)
DEFAULT_PROXY_HTTP = os.getenv("PROXY_HTTP")
DEFAULT_PROXY_HTTPS = os.getenv("PROXY_HTTPS")

# Настройки контента
DEFAULT_WORD_COUNT = int(os.getenv("TARGET_WORD_COUNT", "1750"))
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "ru")

# Настройки расписания
MIN_POST_INTERVAL_HOURS = float(os.getenv("MIN_POST_INTERVAL_HOURS", "24"))
MAX_POST_INTERVAL_HOURS = float(os.getenv("MAX_POST_INTERVAL_HOURS", "72"))
SCHEDULE_JITTER_PERCENT = float(os.getenv("SCHEDULE_JITTER_PERCENT", "30"))

# API настройки (для будущего дашборда)
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "change-me-in-production")

# WordPress Provisioning
WP_CLI_PATH = os.getenv("WP_CLI_PATH", "/usr/local/bin/wp")
DEFAULT_WP_VERSION = os.getenv("DEFAULT_WP_VERSION", "latest")
DEFAULT_WP_LOCALE = os.getenv("DEFAULT_WP_LOCALE", "ru_RU")


class Settings:
    """Класс настроек с валидацией"""

    def __init__(self):
        self.base_dir = BASE_DIR
        self.data_dir = DATA_DIR
        self.logs_dir = LOGS_DIR
        self.database_url = DATABASE_URL
        self.openai_api_key = OPENAI_API_KEY
        self.openai_model = OPENAI_MODEL
        self.dalle_model = DALLE_MODEL
        self.encryption_key = ENCRYPTION_KEY

    def validate(self) -> list:
        """Проверка обязательных настроек"""
        errors = []

        if not self.openai_api_key:
            errors.append("OPENAI_API_KEY не установлен")

        if not self.encryption_key:
            errors.append("ENCRYPTION_KEY не установлен (нужен для шифрования паролей)")

        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0


settings = Settings()
