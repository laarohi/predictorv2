"""Application configuration and settings."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "Predictor v2"
    debug: bool = False
    api_prefix: str = "/api"

    # Database
    database_url: PostgresDsn
    database_echo: bool = False

    # JWT Auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # Football-Data.org
    football_data_token: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"

    # Tournament config
    tournament_config_path: str = "config/worldcup2026.yml"

    # Resend (transactional email).
    # `resend_api_key` blank disables email sending entirely; the email
    # service treats this as a no-op and returns a sentinel rather than
    # erroring, so dev/test environments without a key still boot cleanly.
    resend_api_key: str = ""
    email_from: str = "CxF Predictaa <predictor@laarohi.xyz>"
    # Safety belt for live-fire tests of the deadline batch sender.
    # Comma-separated allowlist of recipient addresses; when set,
    # batch sends skip anyone not in the list (with a logged count).
    # Blank (default) means send to everyone — production behavior.
    # Set on a staging environment to prevent accidentally emailing
    # real users from a cloned DB.
    email_to_allowlist: str = ""

    # Public-facing base URL for the frontend — used to construct
    # links in outbound emails (magic-link login etc.). No trailing
    # slash. Defaults to localhost dev so things work out of the box;
    # production must override via env.
    public_base_url: str = "http://localhost:5173"

    # CORS - stored as string, parsed via computed property
    cors_origins_str: str = "http://localhost:5173,http://localhost:3000"

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from string."""
        v = self.cors_origins_str.strip()
        # Handle JSON array format: ["url1", "url2"]
        if v.startswith("["):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                pass
        # Handle comma-separated format: url1,url2
        return [origin.strip() for origin in v.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def load_tournament_config(path: str | None = None) -> dict[str, Any]:
    """Load tournament configuration from YAML file."""
    settings = get_settings()
    config_path = Path(path or settings.tournament_config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Tournament config not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)


@lru_cache
def get_tournament_config() -> dict[str, Any]:
    """Get cached tournament configuration."""
    return load_tournament_config()


def get_lock_minutes() -> int:
    """Minutes before kickoff that match-score predictions lock.

    Reads `locking.match_lock_before_kickoff` from the tournament YAML.
    Falls back to 15 if the key is missing — chosen so a corrupted config
    fails closed (longer lock window) rather than open.
    """
    config = get_tournament_config()
    locking = config.get("locking") or {}
    value = locking.get("match_lock_before_kickoff", 15)
    return int(value)
