from __future__ import annotations

import re

from .models import JobLead

SENIOR_TERMS = {
    "senior",
    "staff",
    "principal",
    "lead engineer",
    "manager",
    "architect",
    "5+ years",
    "7+ years",
}
INTERNSHIP_TERMS = {"intern", "internship", "six month", "6 month", "off-cycle", "co-op"}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def score_job(job: JobLead, profile: dict) -> tuple[int, str]:
    haystack = _normalize(f"{job.title} {job.description} {job.location}")
    title = _normalize(job.title)

    if any(term in haystack for term in SENIOR_TERMS):
        return 0, ""

    tracks = profile.get("role_tracks", {})
    best_track = ""
    best = 0
    for track_name, track in tracks.items():
        score = 0
        titles = [_normalize(item) for item in track.get("titles", [])]
        skills = [_normalize(item) for item in track.get("skills", [])]
        if any(expected in title or title in expected for expected in titles):
            score += 45
        else:
            title_hits = sum(1 for token in ("engineer", "developer", "ai", "ml") if token in title)
            score += min(20, title_hits * 5)

        skill_hits = sum(1 for skill in skills if skill and skill in haystack)
        score += min(30, skill_hits * 6)
        if any(term in haystack for term in INTERNSHIP_TERMS):
            score += 20
        preferences = [item.lower() for item in profile.get("location_preferences", [])]
        if any(preference in haystack for preference in preferences):
            score += 5
        if score > best:
            best = score
            best_track = track_name
    return min(100, best), best_track

