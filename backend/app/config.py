"""Application configuration loaded from environment variables / .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'cancerbiomap.db').as_posix()}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    score_weight_publication: float = 0.35
    score_weight_source_diversity: float = 0.25
    score_weight_evidence_type: float = 0.25
    score_weight_consistency: float = 0.15
    score_publication_cap: int = 5
    score_min_coverage: float = 0.5
    score_breadth_discount: float = 0.25

    # Optional shared secret for write endpoints (CSV import with dry_run=false, score recompute).
    # When set, requests must send it in the X-Admin-Token header. When empty, writes stay open (local demo).
    admin_token: str = ""

    ncbi_email: str = ""
    ncbi_api_key: str = ""

    @model_validator(mode="after")
    def _check_weights(self) -> "Settings":
        total = (
            self.score_weight_publication
            + self.score_weight_source_diversity
            + self.score_weight_evidence_type
            + self.score_weight_consistency
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Evidence score weights must sum to 1.0 (got {total:.4f})")
        if self.score_publication_cap < 1:
            raise ValueError("SCORE_PUBLICATION_CAP must be >= 1")
        if not 0.0 <= self.score_breadth_discount <= 1.0:
            raise ValueError("SCORE_BREADTH_DISCOUNT must be between 0 and 1")
        return self

    @property
    def resolved_database_url(self) -> str:
        """Resolve relative SQLite paths against the backend directory."""
        url = self.database_url
        prefix = "sqlite:///./"
        if url.startswith(prefix):
            return f"sqlite:///{(BACKEND_DIR / url[len(prefix):]).as_posix()}"
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
