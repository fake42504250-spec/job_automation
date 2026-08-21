from __future__ import annotations

import base64
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .job_sources import decode_subject, gmail_body

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailNotConfigured(RuntimeError):
    pass


class GmailClient:
    def __init__(self, credentials_file: Path, token_file: Path):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self._service = None
        self._address = ""

    def connect(self):
        if self._service is not None:
            return self._service
        if not self.credentials_file.exists():
            raise GmailNotConfigured(
                f"Missing {self.credentials_file}. Download an OAuth desktop-client JSON file first."
            )
        credentials = None
        if self.token_file.exists():
            credentials = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_file), SCOPES)
                credentials = flow.run_local_server(port=0)
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(credentials.to_json(), encoding="utf-8")
        self._service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        self._address = self._service.users().getProfile(userId="me").execute()["emailAddress"]
        return self._service

    @property
    def address(self) -> str:
        self.connect()
        return self._address

    def fetch_alerts(self, label_name: str, max_results: int = 50) -> list[dict]:
        service = self.connect()
        query = f'label:"{label_name}" newer_than:14d'
        response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages: list[dict] = []
        for item in response.get("messages", []):
            raw = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
            headers = {
                header["name"].lower(): header["value"]
                for header in raw.get("payload", {}).get("headers", [])
            }
            messages.append(
                {
                    "id": raw["id"],
                    "thread_id": raw.get("threadId", ""),
                    "subject": decode_subject(headers.get("subject", "Job alert")),
                    "from": headers.get("from", ""),
                    "html": gmail_body(raw.get("payload", {})),
                }
            )
        return messages

    def send(self, to_email: str, subject: str, body: str, thread_id: str = "") -> dict:
        service = self.connect()
        message = EmailMessage()
        message["To"] = to_email
        message["From"] = self.address
        message["Subject"] = subject
        if thread_id:
            thread = (
                service.users()
                .threads()
                .get(
                    userId="me",
                    id=thread_id,
                    format="metadata",
                    metadataHeaders=["Message-ID", "References"],
                )
                .execute()
            )
            last_message = thread.get("messages", [])[-1]
            headers = {
                item["name"].lower(): item["value"]
                for item in last_message.get("payload", {}).get("headers", [])
            }
            parent_message_id = headers.get("message-id", "")
            if parent_message_id:
                message["In-Reply-To"] = parent_message_id
                references = headers.get("references", "").strip()
                message["References"] = f"{references} {parent_message_id}".strip()
        message.set_content(body)
        payload = {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")}
        if thread_id:
            payload["threadId"] = thread_id
        return service.users().messages().send(userId="me", body=payload).execute()

    def thread_has_external_reply(self, thread_id: str) -> bool:
        service = self.connect()
        thread = service.users().threads().get(userId="me", id=thread_id, format="metadata").execute()
        for message in thread.get("messages", [])[1:]:
            headers = {
                item["name"].lower(): item["value"]
                for item in message.get("payload", {}).get("headers", [])
            }
            sender = headers.get("from", "").lower()
            if self.address.lower() not in sender:
                return True
        return False
