from __future__ import annotations

import re
import urllib.robotparser
from collections.abc import Iterable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .models import Contact, JobLead

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PERSONAL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
}
JOB_BOARD_DOMAINS = {
    "linkedin.com",
    "wellfound.com",
    "ycombinator.com",
    "cutshort.io",
    "instahyre.com",
    "indeed.com",
}
ROLE_HINTS = ("recruit", "talent", "career", "jobs", "people", "hr", "hiring")


def valid_corporate_email(email: str) -> bool:
    email = email.strip().lower().strip(".,;:()[]<>")
    if not EMAIL_RE.fullmatch(email):
        return False
    domain = email.rsplit("@", 1)[1]
    return domain not in PERSONAL_DOMAINS and not domain.endswith(".example")


def contacts_from_text(text: str, source_url: str = "") -> list[Contact]:
    contacts: list[Contact] = []
    for email in sorted({match.lower() for match in EMAIL_RE.findall(text)}):
        if not valid_corporate_email(email):
            continue
        local = email.split("@", 1)[0]
        confidence = 90 if any(hint in local for hint in ROLE_HINTS) else 65
        contacts.append(
            Contact(email=email, role="Recruiting or company contact", source_url=source_url, confidence=confidence)
        )
    return contacts


class PublicContactFinder:
    def __init__(self, timeout: float = 10.0):
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "JobAutomation/0.1 (contact discovery; low volume)"},
        )

    def _allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        robots = urllib.robotparser.RobotFileParser()
        try:
            response = self.client.get(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
            if response.status_code >= 400:
                return True
            robots.parse(response.text.splitlines())
            return robots.can_fetch("JobAutomation/0.1", url)
        except httpx.HTTPError:
            return True

    def find(self, job: JobLead) -> list[Contact]:
        found = contacts_from_text(job.description, job.url)
        start_url = job.company_url or job.url
        parsed = urlparse(start_url)
        domain = parsed.netloc.lower().removeprefix("www.")
        if not parsed.scheme.startswith("http") or any(domain.endswith(item) for item in JOB_BOARD_DOMAINS):
            return found
        origin = f"{parsed.scheme}://{parsed.netloc}"
        candidates = [start_url] + [urljoin(origin, path) for path in ("/careers", "/jobs", "/contact", "/team")]
        for url in candidates[:5]:
            if not self._allowed(url):
                continue
            try:
                response = self.client.get(url)
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type", ""):
                    continue
                soup = BeautifulSoup(response.text[:1_000_000], "html.parser")
                found.extend(contacts_from_text(soup.get_text(" "), str(response.url)))
                for link in soup.select('a[href^="mailto:"]'):
                    found.extend(contacts_from_text(link.get("href", "")[7:], str(response.url)))
            except httpx.HTTPError:
                continue
        return deduplicate_contacts(found)


class HunterContactFinder:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def find(self, job: JobLead) -> list[Contact]:
        if not self.api_key:
            return []
        domain = urlparse(job.company_url or job.url).netloc.lower().removeprefix("www.")
        if not domain or any(domain.endswith(item) for item in JOB_BOARD_DOMAINS):
            return []
        try:
            response = httpx.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "api_key": self.api_key, "limit": 10},
                timeout=15,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        contacts: list[Contact] = []
        for item in response.json().get("data", {}).get("emails", []):
            email = (item.get("value") or "").lower()
            position = item.get("position") or ""
            department = item.get("department") or ""
            relevant = any(hint in f"{position} {department}".lower() for hint in ROLE_HINTS)
            if valid_corporate_email(email) and relevant:
                name = " ".join(filter(None, [item.get("first_name"), item.get("last_name")]))
                contacts.append(
                    Contact(
                        email=email,
                        name=name,
                        role=position or department or "Recruiting team",
                        source_url="https://hunter.io",
                        confidence=int(item.get("confidence") or 70),
                    )
                )
        return contacts


def deduplicate_contacts(contacts: Iterable[Contact]) -> list[Contact]:
    best: dict[str, Contact] = {}
    for contact in contacts:
        previous = best.get(contact.email.lower())
        if previous is None or contact.confidence > previous.confidence:
            best[contact.email.lower()] = contact
    return sorted(best.values(), key=lambda item: item.confidence, reverse=True)
