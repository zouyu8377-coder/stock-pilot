from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    TUSHARE_TOKEN: str = ""
    TUSHARE_RATE_LIMIT_SECONDS: int = 0
    TUSHARE_CACHE_ROOT: str = "data/tushare"
    ANALYSIS_SNAPSHOT_DIR: str = "data/analysis_snapshots"
    PORTFOLIO_DATA_DIR: str = "data/portfolio"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    class Config:
        env_file = ".env"


settings = Settings()
