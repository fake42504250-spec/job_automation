from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .models import Contact, JobLead, utc_now

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT NOT NULL,
    company_url TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    source_message_id TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    track TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    confidence INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(job_id, email)
);

CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    attempt INTEGER NOT NULL DEFAULT 1,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    gmail_message_id TEXT NOT NULL DEFAULT '',
    gmail_thread_id TEXT NOT NULL DEFAULT '',
    scheduled_at TEXT NOT NULL DEFAULT '',
    sent_at TEXT NOT NULL DEFAULT '',
    replied_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(contact_id, attempt)
);

CREATE TABLE IF NOT EXISTS suppression (
    email TEXT PRIMARY KEY,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_score ON jobs(status, score DESC);
CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach(status, scheduled_at);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @staticmethod
    def fingerprint(job: JobLead) -> str:
        key = f"{job.company.strip().lower()}|{job.title.strip().lower()}|{job.url.strip()}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def upsert_job(self, job: JobLead) -> int:
        now = utc_now()
        fingerprint = self.fingerprint(job)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    fingerprint, title, company, url, company_url, location, description,
                    source, source_message_id, score, track, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    description=excluded.description,
                    score=MAX(jobs.score, excluded.score),
                    track=CASE WHEN excluded.track <> '' THEN excluded.track ELSE jobs.track END,
                    updated_at=excluded.updated_at
                """,
                (
                    fingerprint,
                    job.title,
                    job.company,
                    job.url,
                    job.company_url,
                    job.location,
                    job.description,
                    job.source,
                    job.source_message_id,
                    job.score,
                    job.track,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT id FROM jobs WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            return int(row["id"])

    def add_contact(self, job_id: int, contact: Contact) -> int | None:
        if self.is_suppressed(contact.email):
            return None
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO contacts (job_id, email, name, role, source_url, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, email) DO UPDATE SET
                    name=CASE WHEN excluded.name <> '' THEN excluded.name ELSE contacts.name END,
                    role=CASE WHEN excluded.role <> '' THEN excluded.role ELSE contacts.role END,
                    confidence=MAX(contacts.confidence, excluded.confidence)
                """,
                (
                    job_id,
                    contact.email.lower(),
                    contact.name,
                    contact.role,
                    contact.source_url,
                    contact.confidence,
                    utc_now(),
                ),
            )
            row = connection.execute(
                "SELECT id FROM contacts WHERE job_id=? AND email=?",
                (job_id, contact.email.lower()),
            ).fetchone()
            return int(row["id"]) if row else None

    def is_suppressed(self, email: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM suppression WHERE email=?", (email.lower(),)
            ).fetchone()
            return row is not None

    def mark_message_processed(self, message_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO processed_messages(message_id, processed_at) VALUES (?, ?)",
                (message_id, utc_now()),
            )

    def message_processed(self, message_id: str) -> bool:
        with self.connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM processed_messages WHERE message_id=?", (message_id,)
                ).fetchone()
                is not None
            )

    def qualified_jobs(self, min_score: int, limit: int = 100) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM jobs
                    WHERE score >= ? AND status IN ('new', 'qualified')
                    ORDER BY score DESC, created_at DESC LIMIT ?
                    """,
                    (min_score, limit),
                )
            )

    def contacts_for_job(self, job_id: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM contacts WHERE job_id=? ORDER BY confidence DESC", (job_id,)
                )
            )

    def queue_outreach(
        self, job_id: int, contact_id: int, attempt: int, subject: str, body: str
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO outreach (
                    job_id, contact_id, attempt, subject, body, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (job_id, contact_id, attempt, subject, body, now, now),
            )

    def queued_outreach(self, limit: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT o.*, c.email, c.name, c.role, j.title, j.company, j.url, j.track,
                        COALESCE((
                            SELECT previous.gmail_thread_id FROM outreach previous
                            WHERE previous.contact_id=o.contact_id
                                AND previous.gmail_thread_id <> ''
                            ORDER BY previous.attempt DESC LIMIT 1
                        ), '') AS parent_thread_id
                    FROM outreach o
                    JOIN contacts c ON c.id=o.contact_id
                    JOIN jobs j ON j.id=o.job_id
                    WHERE o.status='queued'
                    ORDER BY j.score DESC, o.created_at ASC LIMIT ?
                    """,
                    (limit,),
                )
            )

    def mark_sent(self, outreach_id: int, message_id: str, thread_id: str) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE outreach SET status='sent', gmail_message_id=?, gmail_thread_id=?,
                    sent_at=?, updated_at=? WHERE id=?
                """,
                (message_id, thread_id, now, now, outreach_id),
            )

    def mark_replied(self, outreach_id: int) -> None:
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT contact_id FROM outreach WHERE id=?", (outreach_id,)
            ).fetchone()
            if not row:
                return
            connection.execute(
                "UPDATE outreach SET status='replied', replied_at=?, updated_at=? WHERE id=?",
                (now, now, outreach_id),
            )
            connection.execute(
                """
                UPDATE outreach SET status='cancelled', updated_at=?
                WHERE contact_id=? AND status='queued'
                """,
                (now, row["contact_id"]),
            )

    def outreach_count_for_company(self, company: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(DISTINCT lower(c.email)) AS count
                FROM outreach o
                JOIN contacts c ON c.id=o.contact_id
                JOIN jobs j ON j.id=o.job_id
                WHERE lower(j.company)=lower(?) AND o.status <> 'cancelled'
                """,
                (company,),
            ).fetchone()
            return int(row["count"])

    def sent_outreach(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT o.*, c.email, c.name, c.role, j.title, j.company, j.url, j.track
                    FROM outreach o
                    JOIN contacts c ON c.id=o.contact_id
                    JOIN jobs j ON j.id=o.job_id
                    WHERE o.status='sent' AND o.gmail_thread_id <> ''
                    ORDER BY o.sent_at ASC
                    """
                )
            )

    def sent_today_count(self) -> int:
        today = datetime.now(UTC).date().isoformat()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM outreach WHERE status='sent' AND substr(sent_at,1,10)=?",
                (today,),
            ).fetchone()
            return int(row["count"])

    def update_job_status(self, job_id: int, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE jobs SET status=?, updated_at=? WHERE id=?", (status, utc_now(), job_id)
            )

    def dashboard(self) -> dict:
        with self.connect() as connection:
            counts = {
                "jobs": connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                "qualified": connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status IN ('qualified','contacted')"
                ).fetchone()[0],
                "contacts": connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0],
                "queued": connection.execute(
                    "SELECT COUNT(*) FROM outreach WHERE status='queued'"
                ).fetchone()[0],
                "sent": connection.execute(
                    "SELECT COUNT(*) FROM outreach WHERE status='sent'"
                ).fetchone()[0],
                "replied": connection.execute(
                    "SELECT COUNT(*) FROM outreach WHERE status='replied'"
                ).fetchone()[0],
            }
            jobs = list(
                connection.execute(
                    "SELECT * FROM jobs ORDER BY score DESC, created_at DESC LIMIT 40"
                )
            )
            outreach = list(
                connection.execute(
                    """
                    SELECT o.*, c.email, j.company, j.title FROM outreach o
                    JOIN contacts c ON c.id=o.contact_id JOIN jobs j ON j.id=o.job_id
                    ORDER BY o.created_at DESC LIMIT 40
                    """
                )
            )
            return {"counts": counts, "jobs": jobs, "outreach": outreach}
