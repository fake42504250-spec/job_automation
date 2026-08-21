from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


def _bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    root_dir: Path
    dry_run: bool
    timezone: str
    run_at: str
    daily_send_limit: int
    min_job_score: int
    max_contacts_per_company: int
    follow_up_days: tuple[int, ...]
    gmail_job_alert_label: str
    gmail_credentials_file: Path
    gmail_token_file: Path
    profile_file: Path
    database_file: Path
    hunter_api_key: str
    job_feed_urls: tuple[str, ...]
    profile: dict = field(default_factory=dict)

    @property
    def data_dir(self) -> Path:
        return self.database_file.parent

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profile_file.parent.mkdir(parents=True, exist_ok=True)


def load_settings(root_dir: Path | None = None) -> Settings:
    root = (root_dir or Path.cwd()).resolve()
    load_dotenv(root / ".env")

    def path_env(name: str, default: str) -> Path:
        value = Path(os.getenv(name, default))
        return value if value.is_absolute() else root / value

    followups = tuple(int(day) for day in _csv(os.getenv("FOLLOW_UP_DAYS", "4,9")))
    settings = Settings(
        root_dir=root,
        dry_run=_bool(os.getenv("DRY_RUN"), True),
        timezone=os.getenv("TIMEZONE", "Asia/Kolkata"),
        run_at=os.getenv("RUN_AT", "09:00"),
        daily_send_limit=max(1, int(os.getenv("DAILY_SEND_LIMIT", "8"))),
        min_job_score=max(0, min(100, int(os.getenv("MIN_JOB_SCORE", "60")))),
        max_contacts_per_company=max(1, int(os.getenv("MAX_CONTACTS_PER_COMPANY", "2"))),
        follow_up_days=followups or (4, 9),
        gmail_job_alert_label=os.getenv("GMAIL_JOB_ALERT_LABEL", "Job Alerts"),
        gmail_credentials_file=path_env(
            "GMAIL_CREDENTIALS_FILE", "config/gmail_credentials.json"
        ),
        gmail_token_file=path_env("GMAIL_TOKEN_FILE", "data/gmail_token.json"),
        profile_file=path_env("PROFILE_FILE", "config/profile.yaml"),
        database_file=path_env("DATABASE_FILE", "data/job_automation.db"),
        hunter_api_key=os.getenv("HUNTER_API_KEY", "").strip(),
        job_feed_urls=tuple(_csv(os.getenv("JOB_FEED_URLS"))),
    )
    settings.ensure_directories()
    if settings.profile_file.exists():
        settings.profile = yaml.safe_load(settings.profile_file.read_text(encoding="utf-8")) or {}
    return settings


def initialize_project(settings: Settings) -> list[Path]:
    """Create user-owned configuration files without overwriting existing values."""
    created: list[Path] = []
    env_file = settings.root_dir / ".env"
    env_example = settings.root_dir / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copyfile(env_example, env_file)
        created.append(env_file)

    profile_example = settings.root_dir / "config" / "profile.example.yaml"
    if not settings.profile_file.exists() and profile_example.exists():
        shutil.copyfile(profile_example, settings.profile_file)
        created.append(settings.profile_file)
    settings.ensure_directories()
    return created

