from __future__ import annotations

from .models import Contact, EmailDraft, JobLead


def _first_name(name: str) -> str:
    return name.strip().split()[0] if name.strip() else "there"


def compose_initial(job: JobLead, contact: Contact, profile: dict) -> EmailDraft:
    track = profile.get("role_tracks", {}).get(job.track, {})
    proof = track.get("proof") or "I have built production-style software projects."
    achievement = next(iter(profile.get("achievements", [])), "")
    links = [f"Resume: {profile.get('resume_url', '')}", f"GitHub: {profile.get('github_url', '')}"]
    if profile.get("portfolio_url"):
        links.append(f"Portfolio: {profile['portfolio_url']}")
    links_text = "\n".join(link for link in links if not link.endswith(": "))
    subject = f"Six-month {job.track or 'software'} internship | {profile.get('college', 'student')}"
    body = f"""Hi {_first_name(contact.name)},

I’m {profile.get('name', 'a final-year computer science student')} from {profile.get('college', 'my university')}, and I’m interested in the {job.title} opportunity at {job.company}.

My closest relevant experience: {proof} {achievement}

Would you be open to considering my profile or directing me to the appropriate recruiter if the fit is reasonable?

Job: {job.url}
{links_text}

Thank you,
{profile.get('name', '')}

If this is not relevant, please reply “no” and I will not follow up.
"""
    return EmailDraft(to_email=contact.email, subject=subject, body=body.strip(), attempt=1)


def compose_follow_up(previous: dict, attempt: int, profile: dict) -> EmailDraft:
    if attempt == 2:
        message = (
            f"I’m following up once regarding the {previous['title']} opportunity at "
            f"{previous['company']}. My background appears relevant, and I would appreciate "
            "being directed to the appropriate person if another team owns this role."
        )
    else:
        message = (
            f"This is my final follow-up regarding six-month internship opportunities at "
            f"{previous['company']}. I would be glad to share a short project demo or complete "
            "an assessment. No worries if there is no suitable opening currently."
        )
    body = f"""Hi {_first_name(previous['name'])},

{message}

Job: {previous['url']}
Resume: {profile.get('resume_url', '')}

Thank you,
{profile.get('name', '')}
"""
    previous_subject = previous["subject"]
    subject = previous_subject if previous_subject.lower().startswith("re:") else f"Re: {previous_subject}"
    return EmailDraft(
        to_email=previous["email"],
        subject=subject,
        body=body.strip(),
        attempt=attempt,
    )
