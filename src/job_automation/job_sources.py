from __future__ import annotations

import base64
import hashlib
import re
import xml.etree.ElementTree as ET
from email.header import decode_header, make_header
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from .models import JobLead

BLOCKED_LINK_TERMS = {
    "unsubscribe",
    "privacy",
    "preferences",
    "help",
    "support",
    "view in browser",
    "manage alert",
}


def decode_subject(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except (UnicodeError, LookupError, ValueError):
        return value


def unwrap_redirect(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("url", "q", "target", "redirect", "dest", "destination"):
        candidate = query.get(key, [""])[0]
        if candidate.startswith("http"):
            return unquote(candidate)
    return url


def infer_company(subject: str, surrounding_text: str, title: str) -> str:
    patterns = [
        r"\bat\s+([A-Z][\w&. -]{1,50})",
        r"jobs?\s+(?:from|at)\s+([A-Z][\w&. -]{1,50})",
        r"([A-Z][\w&. -]{1,50})\s+is hiring",
    ]
    for text in (title, surrounding_text, subject):
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip(" -|,.")
    return "Unknown company"


def parse_job_alert_html(html: str, subject: str, source_message_id: str) -> list[JobLead]:
    soup = BeautifulSoup(html, "html.parser")
    leads: list[JobLead] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        title = " ".join(anchor.get_text(" ", strip=True).split())
        url = unwrap_redirect(unescape(anchor.get("href", "")))
        lowered = f"{title} {url}".lower()
        if not title or len(title) < 4 or len(title) > 140 or not url.startswith("http"):
            continue
        if any(term in lowered for term in BLOCKED_LINK_TERMS):
            continue
        if not any(term in lowered for term in ("job", "intern", "engineer", "developer", "career", "apply")):
            continue
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        parent_text = " ".join(anchor.parent.get_text(" ", strip=True).split())[:500]
        company = infer_company(subject, parent_text, title)
        leads.append(
            JobLead(
                title=title,
                company=company,
                url=url,
                description=parent_text,
                source="gmail-alert",
                source_message_id=source_message_id,
            )
        )
    return leads[:30]


def gmail_body(payload: dict) -> str:
    html_parts: list[str] = []
    text_parts: list[str] = []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data:
            decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                "utf-8", errors="replace"
            )
            if mime == "text/html":
                html_parts.append(decoded)
            elif mime == "text/plain":
                text_parts.append(decoded)
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    if html_parts:
        return "\n".join(html_parts)
    plain = "\n".join(text_parts)
    return f"<pre>{plain}</pre>"


def parse_feed(xml_text: str, source_url: str) -> list[JobLead]:
    root = ET.fromstring(xml_text)
    leads: list[JobLead] = []
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for item in items[:50]:
        title = item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or ""
        link = item.findtext("link") or ""
        if not link:
            link_node = item.find("{http://www.w3.org/2005/Atom}link")
            link = link_node.get("href", "") if link_node is not None else ""
        description = (
            item.findtext("description")
            or item.findtext("{http://www.w3.org/2005/Atom}summary")
            or ""
        )
        clean_description = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
        company = infer_company(title, clean_description, title)
        if title and link:
            leads.append(
                JobLead(
                    title=title.strip(),
                    company=company,
                    url=link.strip(),
                    description=clean_description[:3000],
                    source=source_url,
                )
            )
    return leads


def fetch_feeds(urls: tuple[str, ...]) -> list[JobLead]:
    leads: list[JobLead] = []
    with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": "JobAutomation/0.1"}) as client:
        for url in urls:
            try:
                response = client.get(url)
                response.raise_for_status()
                leads.extend(parse_feed(response.text, url))
            except (httpx.HTTPError, ET.ParseError):
                continue
    return leads
