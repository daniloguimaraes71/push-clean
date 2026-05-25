from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://chore:chore@localhost:5432/chorecast"
    test_database_url: str = "postgresql+asyncpg://chore:chore@localhost:5432/chorecast_test"
    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-v4-flash:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_live: bool = False
    vision_enabled: bool = False
    vision_model: str = ""
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
