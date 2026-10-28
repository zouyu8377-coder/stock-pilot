from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    AGENT_REVIEW_MODEL: str = ""
    AGENT_REVIEW_MAX_TOKENS: int = 12000
    AGENT_REVIEW_THINKING: str = "auto"
    AGENT_REVIEW_TIMEOUT_SECONDS: int = 360
    AGENT_REVIEW_REQUEST_TIMEOUT_SECONDS: int = 540
    TUSHARE_TOKEN: str = ""
    TUSHARE_RATE_LIMIT_SECONDS: int = 0
    TUSHARE_CACHE_ROOT: str = "data/tushare"
    ANALYSIS_SNAPSHOT_DIR: str = "data/analysis_snapshots"
    PORTFOLIO_DATA_DIR: str = "data/portfolio"
    PORTFOLIO_VISION_PROVIDER: str = "local_noop"
    VOLCENGINE_ARK_VISION_ENABLED: bool = False
    VOLCENGINE_ARK_VISION_BASE_URL: str = ""
    VOLCENGINE_ARK_VISION_API_KEY: str = ""
    VOLCENGINE_ARK_VISION_MODEL: str = ""
    VOLCENGINE_ARK_VISION_TIMEOUT: int = 120
    VOLCENGINE_ARK_VISION_MAX_TOKENS: int = 4096
    VOLCENGINE_ARK_VISION_RETRY_MAX_TOKENS: int = 8192
    VOLCENGINE_ARK_VISION_SEGMENT_MAX_TOKENS: int = 4096
    VOLCENGINE_ARK_VISION_THINKING_MODE: str = "disabled"
    VOLCENGINE_ARK_VISION_JSON_MODE: bool = True
    DISCLOSURE_VERIFICATION_ENABLED: bool = True
    DISCLOSURE_VERIFICATION_MAX_SYMBOLS: int = 8
    DISCLOSURE_VERIFICATION_MAX_DOCUMENTS: int = 2
    DISCLOSURE_VERIFICATION_CACHE_DAYS: int = 7
    DISCLOSURE_INDEX_CHECK_MINUTES: int = 60
    DASHBOARD_CACHE_SECONDS: int = 300
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    CORS_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1):\d+$"

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
