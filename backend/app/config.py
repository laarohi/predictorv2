"""Application configuration and settings."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import PostgresDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder/example secrets shipped in this repo (docker-compose, .env.example).
# None of these may ever be the live signing key in production — a forgeable JWT
# key lets anyone mint an admin token.
_WEAK_JWT_SECRETS = frozenset(
    {
        "super-secret-dev-key-change-in-prod",
        "your-super-secret-key-change-in-production",
        "changeme",
        "secret",
        "test-secret-key",
    }
)


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

    # Admin bootstrap: comma-separated emails auto-granted admin on account
    # creation or login. A fresh deploy otherwise has no admin at all
    # (is_admin can only be toggled by an existing admin). See also
    # scripts/make_admin.py for promoting an existing account.
    admin_emails_str: str = ""

    # Open self-registration toggle. Set false once the friend group is
    # onboarded so outsiders can't join the live pool; existing users keep
    # logging in via password / magic-link / Google.
    registration_enabled: bool = True

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

    # Web Push (VAPID). Blank public/private keys disable push entirely —
    # the push sender treats it as a no-op (mirrors resend_api_key). The
    # private key signs each push JWT; the public key is served to browsers
    # as the applicationServerKey. vapid_subject MUST be a real mailto: or
    # https: URL — iOS rejects a junk/placeholder subject with 403 BadJwtToken.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:aarohiluke@gmail.com"

    # Daily Drop morning broadcast: once local time passes daily_drop_hour:minute
    # (interpreted in the daily_drop_tz timezone) the scheduler builds that day's
    # Drop and pushes "it's in" to every subscriber — once per day (idempotent).
    # Set DAILY_DROP_HOUR=99 to pause the broadcast (the clock never reaches 99).
    daily_drop_hour: int = 8
    daily_drop_minute: int = 30
    daily_drop_tz: str = "Europe/Malta"

    # Claude Code subscription token for the LLM-written Daily Drop roast
    # (Phase C). Mint with `claude setup-token`; set it in .env as
    # CLAUDE_CODE_OAUTH_TOKEN. It is consumed by the `roaster` sidecar (not the
    # backend) — the backend reaches the sidecar over HTTP. IMPORTANT: in the
    # roaster, ANTHROPIC_API_KEY must be UNSET so the subscription token wins the
    # auth precedence (else you'd be billed per-token to an API account).
    claude_code_oauth_token: str = ""

    # Roaster sidecar base URL. The Daily Drop build POSTs the assembled prompt
    # here to get the savage roast. Blank (or unreachable, e.g. prod where the
    # sidecar isn't running) → the roast falls back to the deterministic stand-in.
    roaster_url: str = "http://roaster:8787"

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

    @computed_field
    @property
    def admin_emails(self) -> list[str]:
        """Normalized (lowercased) admin allowlist from admin_emails_str."""
        return [e.strip().lower() for e in self.admin_emails_str.split(",") if e.strip()]

    @model_validator(mode="after")
    def _enforce_secret_strength(self) -> "Settings":
        """Fail closed in production if the JWT secret is weak or a known default.

        Only enforced when ``debug`` is False, so local dev/test stay ergonomic.
        The signing key is the entire trust anchor for auth, the blind pool,
        scoring, and admin ops; booting prod with a placeholder secret should
        crash loudly rather than start silently forgeable.
        """
        if not self.debug:
            key = self.jwt_secret_key or ""
            if key in _WEAK_JWT_SECRETS or len(key) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY is unset, shorter than 32 chars, or a known "
                    "default placeholder. Set a strong secret in production, e.g. "
                    'python -c "import secrets; print(secrets.token_urlsafe(48))"'
                )
        return self


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
