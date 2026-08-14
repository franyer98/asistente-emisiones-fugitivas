from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "cambia-esto"
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    DATABASE_URL: str = ""

    class Config:
        env_file = ".env"

    @property
    def db_url(self) -> str:
        return self.DATABASE_URL or "sqlite:///./asistente.db"


settings = Settings()
