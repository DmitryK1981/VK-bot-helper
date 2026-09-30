"""Централизованная конфигурация (значения берутся из .env / переменных окружения)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # VK
    vk_token: SecretStr

    # ProxyAPI / Gemini
    proxyapi_key: SecretStr
    proxyapi_base_url: str = "https://api.proxyapi.ru"
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_fallback_model: str = ""
    gemini_temperature: float = Field(0.7, ge=0.0, le=2.0)
    gemini_max_output_tokens: int = Field(2048, gt=0)
    ai_timeout_seconds: float = Field(60.0, gt=0)
    ai_max_retries: int = Field(2, ge=0, le=5)

    # Бот
    users_dir: Path = Path("users")
    max_history_messages: int = Field(100, gt=0)
    max_dialogs_per_user: int = Field(8, gt=0, le=8)  # ограничено размером клавиатуры VK
    max_user_message_length: int = Field(4000, gt=0)

    # Защита от спама: не более N запросов к ИИ за окно (секунд) на пользователя
    rate_limit_requests: int = Field(8, gt=0)
    rate_limit_window_seconds: float = Field(60.0, gt=0)

    # Суммаризация: сколько старых сообщений сворачивать в краткое содержание за раз
    summary_batch_size: int = Field(20, gt=0)
    summary_max_chars: int = Field(1500, gt=0)

    # Стриминг: минимальный интервал между правками сообщения в VK (сек)
    stream_edit_interval: float = Field(1.5, gt=0)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
