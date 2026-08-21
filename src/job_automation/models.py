from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class JobLead:
    title: str
    company: str
    url: str
    location: str = ""
    description: str = ""
    source: str = "unknown"
    source_message_id: str = ""
    company_url: str = ""
    score: int = 0
    track: str = ""


@dataclass(slots=True)
class Contact:
    email: str
    name: str = ""
    role: str = "Recruiting team"
    source_url: str = ""
    confidence: int = 50


@dataclass(slots=True)
class EmailDraft:
    to_email: str
    subject: str
    body: str
    attempt: int = 1

