from pathlib import Path

from job_automation.db import Database
from job_automation.models import Contact, JobLead


def test_database_deduplicates_jobs_and_contacts(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    job = JobLead(title="SDE Intern", company="Acme", url="https://acme.test/jobs/1")
    first_id = database.upsert_job(job)
    second_id = database.upsert_job(job)
    assert first_id == second_id

    contact = Contact(email="careers@acme.test", confidence=90)
    first_contact = database.add_contact(first_id, contact)
    second_contact = database.add_contact(first_id, contact)
    assert first_contact == second_contact
    assert database.dashboard()["counts"]["jobs"] == 1


def test_reply_cancels_queued_follow_up(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    job_id = database.upsert_job(
        JobLead(title="SDE Intern", company="Acme", url="https://acme.test/jobs/1")
    )
    contact_id = database.add_contact(job_id, Contact(email="careers@acme.test"))
    assert contact_id is not None
    database.queue_outreach(job_id, contact_id, 1, "Subject", "Body")
    initial = database.queued_outreach(1)[0]
    database.mark_sent(initial["id"], "message-1", "thread-1")
    database.queue_outreach(job_id, contact_id, 2, "Re: Subject", "Follow-up")
    database.mark_replied(initial["id"])
    assert database.queued_outreach(10) == []
    assert database.outreach_count_for_company("acme") == 1
