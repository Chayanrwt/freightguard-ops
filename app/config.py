from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = ""
    gemini_api_key: str = ""
    ocr_backend: str = "rapidocr"  # "rapidocr" or "textract"
    confidence_threshold: float = 0.85
    high_value_threshold_usd: float = 10000.0
    database_url: str = "sqlite:///./data/freightguard.db"
    chroma_path: str = "./data/chroma_db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
