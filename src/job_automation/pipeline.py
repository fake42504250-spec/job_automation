from __future__ import annotations

import logging
from datetime import UTC, datetime

from .composer import compose_follow_up, compose_initial
from .config import Settings
from .contacts import HunterContactFinder, PublicContactFinder, deduplicate_contacts
from .db import Database
from .gmail import GmailClient, GmailNotConfigured
from .job_sources import fetch_feeds, parse_job_alert_html
from .models import Contact, JobLead
from .scoring import score_job

LOGGER = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.database_file)
        self.db.initialize()
        self.gmail = GmailClient(settings.gmail_credentials_file, settings.gmail_token_file)
        self.public_contacts = PublicContactFinder()
        self.hunter_contacts = HunterContactFinder(settings.hunter_api_key)

    def ingest(self) -> int:
        leads: list[JobLead] = fetch_feeds(self.settings.job_feed_urls)
        try:
            for message in self.gmail.fetch_alerts(self.settings.gmail_job_alert_label):
                if self.db.message_processed(message["id"]):
                    continue
                leads.extend(
                    parse_job_alert_html(message["html"], message["subject"], message["id"])
                )
                self.db.mark_message_processed(message["id"])
        except GmailNotConfigured as exc:
            LOGGER.warning("Gmail ingestion skipped: %s", exc)

        inserted = 0
        for lead in leads:
            lead.score, lead.track = score_job(lead, self.settings.profile)
            self.db.upsert_job(lead)
            inserted += 1
        return inserted

    @staticmethod
    def _row_to_job(row) -> JobLead:
        return JobLead(
            title=row["title"],
            company=row["company"],
            url=row["url"],
            company_url=row["company_url"],
            location=row["location"],
            description=row["description"],
            source=row["source"],
            score=row["score"],
            track=row["track"],
        )

    def discover_contacts_and_queue(self) -> int:
        queued = 0
        for row in self.db.qualified_jobs(self.settings.min_job_score):
            job = self._row_to_job(row)
            company_count = self.db.outreach_count_for_company(job.company)
            remaining_company_slots = self.settings.max_contacts_per_company - company_count
            if remaining_company_slots <= 0:
                self.db.update_job_status(row["id"], "company_cap_reached")
                continue
            contacts = self.db.contacts_for_job(row["id"])
            if not contacts:
                discovered = deduplicate_contacts(
                    [
                        *self.public_contacts.find(job),
                        *self.hunter_contacts.find(job),
                    ]
                )[:remaining_company_slots]
                for contact in discovered:
                    self.db.add_contact(row["id"], contact)
                contacts = self.db.contacts_for_job(row["id"])

            for contact_row in contacts[:remaining_company_slots]:
                contact = Contact(
                    email=contact_row["email"],
                    name=contact_row["name"],
                    role=contact_row["role"],
                    source_url=contact_row["source_url"],
                    confidence=contact_row["confidence"],
                )
                draft = compose_initial(job, contact, self.settings.profile)
                self.db.queue_outreach(
                    row["id"], contact_row["id"], draft.attempt, draft.subject, draft.body
                )
                queued += 1
            self.db.update_job_status(row["id"], "qualified" if contacts else "no_contact")
        return queued

    def send_queued(self) -> int:
        remaining = max(0, self.settings.daily_send_limit - self.db.sent_today_count())
        if remaining == 0 or self.settings.dry_run:
            return 0
        required_profile_fields = ("name", "college", "resume_url", "github_url")
        missing = []
        for field in required_profile_fields:
            value = str(self.settings.profile.get(field, "")).strip().lower()
            if not value or "replace" in value or value.startswith("your "):
                missing.append(field)
        if missing:
            raise RuntimeError(f"Live sending blocked; profile fields are missing: {', '.join(missing)}")
        sent = 0
        for row in self.db.queued_outreach(remaining):
            response = self.gmail.send(
                row["email"], row["subject"], row["body"], row["parent_thread_id"]
            )
            self.db.mark_sent(row["id"], response.get("id", ""), response.get("threadId", ""))
            self.db.update_job_status(row["job_id"], "contacted")
            sent += 1
        return sent

    def check_replies_and_followups(self) -> tuple[int, int]:
        replies = 0
        followups = 0
        now = datetime.now(UTC)
        for row in self.db.sent_outreach():
            if self.gmail.thread_has_external_reply(row["gmail_thread_id"]):
                self.db.mark_replied(row["id"])
                replies += 1
                continue
            sent_at = datetime.fromisoformat(row["sent_at"])
            age_days = (now - sent_at).days
            next_attempt = row["attempt"] + 1
            if next_attempt > 3:
                continue
            threshold_index = min(next_attempt - 2, len(self.settings.follow_up_days) - 1)
            if age_days < self.settings.follow_up_days[threshold_index]:
                continue
            draft = compose_follow_up(dict(row), next_attempt, self.settings.profile)
            self.db.queue_outreach(
                row["job_id"], row["contact_id"], next_attempt, draft.subject, draft.body
            )
            followups += 1
        return replies, followups

    def run_once(self) -> dict[str, int | bool]:
        ingested = self.ingest()
        queued = self.discover_contacts_and_queue()
        replies = 0
        followups = 0
        try:
            replies, followups = self.check_replies_and_followups()
        except GmailNotConfigured:
            pass
        sent = self.send_queued()
        result = {
            "ingested": ingested,
            "queued": queued,
            "sent": sent,
            "replies": replies,
            "followups": followups,
            "dry_run": self.settings.dry_run,
        }
        LOGGER.info("Pipeline completed: %s", result)
        return result
