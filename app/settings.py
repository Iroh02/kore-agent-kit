"""Settings. Everything from env / .env, nothing hardcoded.

Deliberately: no setting is fatal by absence. A missing key degrades that
one capability to a typed error the bot can speak, per the hard constraint
in CLAUDE.md. `python -m app.api` must always start.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Claude -----------------------------------------------------------
    anthropic_api_key: str = ""
    extraction_model: str = "claude-opus-5"

    # --- Microsoft Teams bot ---------------------------------------------
    # From the Azure Bot resource. Blank = channel disabled, app still runs.
    ms_app_id: str = ""
    ms_app_password: str = ""
    ms_tenant_id: str = ""

    # --- Speech to text ---------------------------------------------------
    # DECISIONS.md D14: pick one, don't revisit.
    stt_provider: str = "mock-stt"  # deepgram-nova-3 | azure-speech-standard
    stt_api_key: str = ""

    # --- App --------------------------------------------------------------
    port: int = 8000
    db_path: str = "kore.db"
    # Confidence below this flags a lead for review instead of trusting it.
    min_confidence: float = 0.6
    # Poll interval for due follow-ups.
    scheduler_seconds: int = 30

    @property
    def claude_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def teams_enabled(self) -> bool:
        return bool(self.ms_app_id and self.ms_app_password)

    @property
    def stt_enabled(self) -> bool:
        return bool(self.stt_api_key) or self.stt_provider == "mock-stt"


settings = Settings()
