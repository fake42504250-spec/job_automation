from job_automation.models import JobLead
from job_automation.scoring import score_job

PROFILE = {
    "location_preferences": ["India", "Remote"],
    "role_tracks": {
        "backend": {
            "titles": ["software engineer intern", "backend intern"],
            "skills": ["Python", "FastAPI", "SQL"],
        },
        "genai": {
            "titles": ["genai intern", "ai engineer intern"],
            "skills": ["RAG", "LangGraph", "embeddings"],
        },
    },
}


def test_backend_internship_scores_high():
    job = JobLead(
        title="Software Engineer Intern",
        company="Example",
        url="https://example.com/jobs/1",
        location="India Remote",
        description="Six month internship using Python, FastAPI and SQL.",
    )
    score, track = score_job(job, PROFILE)
    assert score >= 80
    assert track == "backend"


def test_senior_role_is_rejected():
    job = JobLead(
        title="Senior Backend Engineer",
        company="Example",
        url="https://example.com/jobs/2",
        description="Python and FastAPI; 7+ years required.",
    )
    assert score_job(job, PROFILE) == (0, "")

