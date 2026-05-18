from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./price_tracker.db"
    telegram_bot_token: str = ""
    check_interval_hours: int = 6
    default_threshold_percent: float = 5.0
    log_level: str = "INFO"


settings = Settings()