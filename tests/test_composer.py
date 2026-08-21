from job_automation.composer import compose_follow_up, compose_initial
from job_automation.models import Contact, JobLead


def test_composer_uses_job_and_profile_evidence():
    job = JobLead(
        title="Backend Intern",
        company="Acme",
        url="https://acme.test/jobs/1",
        track="backend",
    )
    contact = Contact(email="talent@acme.test", name="Riya Singh")
    profile = {
        "name": "Candidate",
        "college": "Example Institute",
        "resume_url": "https://example.test/resume",
        "github_url": "https://github.com/example",
        "role_tracks": {"backend": {"proof": "Built 20 REST APIs."}},
        "achievements": ["Solved 800+ DSA problems."],
    }
    draft = compose_initial(job, contact, profile)
    assert "Hi Riya" in draft.body
    assert "Built 20 REST APIs" in draft.body
    assert job.url in draft.body


def test_follow_up_does_not_repeat_re_prefix():
    previous = {
        "title": "Backend Intern",
        "company": "Acme",
        "name": "Riya",
        "email": "talent@acme.test",
        "url": "https://acme.test/jobs/1",
        "subject": "Re: Original subject",
    }
    draft = compose_follow_up(previous, 3, {"name": "Candidate", "resume_url": "resume"})
    assert draft.subject == "Re: Original subject"
