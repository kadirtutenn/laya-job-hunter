"""
Application Status & Email Inbox Agent:
Watches incoming job-hunt emails (via IMAP or local storage),
classifies messages using local Laya decision models, updates job application
status in local SQLite storage, and triggers macOS desktop alerts for interviews.
"""

from __future__ import annotations

import email
import hashlib
import imaplib
import logging
import re
from datetime import datetime
from email.header import decode_header
from typing import Any, Dict, List, Optional
from job_hunter.laya_client import LayaClient
from job_hunter.models import EmailEvent, ScoredJob
from job_hunter.notifier import DesktopNotifier
from job_hunter.storage import LocalBrainStorage

logger = logging.getLogger(__name__)


def clean_header_str(val: Any) -> str:
    if not val:
        return ""
    decoded_list = decode_header(val)
    parts = []
    for text, enc in decoded_list:
        if isinstance(text, bytes):
            parts.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            parts.append(str(text))
    return " ".join(parts).strip()


class EmailInboxWatcher:
    """Monitors job application emails and automatically updates pipeline statuses."""

    CATEGORIES = {
        "interview_invitation": "Invitation to interview, technical round, recruiter chat, or calendar scheduling",
        "assessment_test": "Coding challenge, technical assessment, take-home project, or test link",
        "application_received": "Confirmation that an application has been received or submitted",
        "rejection": "Rejection notice, unfortunately decided to pursue other candidates, role closed",
        "irrelevant": "Marketing, spam, newsletters, or messages unrelated to active job applications",
    }

    def __init__(
        self,
        laya_client: LayaClient,
        storage: LocalBrainStorage,
        enable_notifications: bool = True,
    ):
        self.client = laya_client
        self.storage = storage
        self.enable_notifications = enable_notifications

    def triage_email(
        self,
        subject: str,
        sender: str,
        body: str,
        message_id: Optional[str] = None,
    ) -> EmailEvent:
        """
        Classifies an email using Laya Decision Model, links to active job, and updates status.
        """
        # Create deterministic event id
        raw_id = message_id or f"{sender}:{subject}:{body[:100]}"
        event_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]

        # 1. Classify with Laya Decision Head
        body_snippet = body[:1500].strip()
        state = (
            f"Email Subject: {subject}\n"
            f"Email Sender: {sender}\n"
            f"Email Body Snippet:\n{body_snippet}"
        )

        questions = {
            "category": {
                "type": "choice",
                "instructions": "Classify this email in relation to the user's job hunt.",
                "criteria": self.CATEGORIES,
            }
        }

        category = "irrelevant"
        confidence = 0.5
        if self.client.is_available():
            try:
                resp = self.client.decide(state=state, questions=questions)
                answers = resp.get("answers", {}).get("category", {})
                choice = answers.get("choice")
                if choice in self.CATEGORIES:
                    category = choice
                    probs = answers.get("probabilities", {})
                    confidence = float(probs.get(choice, 0.8))
            except Exception as e:
                logger.warning(f"Laya email triage error: {e}")

        # Fallback keyword heuristics if Laya daemon unavailable
        if category == "irrelevant":
            lower_comb = f"{subject} {body_snippet}".lower()
            if any(k in lower_comb for k in ["interview", "invitation", "schedule a call", "speak with", "chat with the team", "calendly"]):
                category = "interview_invitation"
            elif any(k in lower_comb for k in ["assessment", "hackerrank", "codility", "take-home", "technical challenge"]):
                category = "assessment_test"
            elif any(k in lower_comb for k in ["unfortunately", "pursue other", "not moving forward", "position has been filled"]):
                category = "rejection"
            elif any(k in lower_comb for k in ["application received", "thank you for applying", "we have received your application"]):
                category = "application_received"

        # 2. Extract Company Name and match with local storage
        matched_job = self._match_job_from_email(subject, sender, body_snippet)
        action_taken = "no_action"
        matched_job_id = matched_job.job.id if matched_job else None
        matched_company = matched_job.job.company if matched_job else self._infer_company(sender, subject)

        # 3. Automatic Status Transitions
        if matched_job:
            if category == "interview_invitation":
                self.storage.update_status(matched_job.job.id, "interview_scheduled")
                action_taken = f"Updated job status to 'interview_scheduled'"
            elif category == "assessment_test":
                self.storage.update_status(matched_job.job.id, "assessment")
                action_taken = f"Updated job status to 'assessment'"
            elif category == "rejection":
                self.storage.update_status(matched_job.job.id, "rejected")
                action_taken = f"Updated job status to 'rejected'"
            elif category == "application_received":
                if matched_job.status in ("inbox", "shortlisted"):
                    self.storage.update_status(matched_job.job.id, "applied")
                    action_taken = f"Confirmed application status as 'applied'"

        # 4. Trigger High-Priority macOS Desktop Notification for Interviews
        if self.enable_notifications and category in ("interview_invitation", "assessment_test"):
            company_display = matched_company or "Kariyer Bildirimi"
            if category == "interview_invitation":
                title = "🎉 Mülakat Daveti Alındı! | Ollaya Career"
                subtitle = f"{company_display}: {subject[:50]}"
                msg = "Tebrikler! İş başvurunuz için mülakat veya görüşme daveti geldi."
            else:
                title = "📝 Teknik Değerlendirme / Test! | Ollaya Career"
                subtitle = f"{company_display}: {subject[:50]}"
                msg = "İş başvurunuz için teknik test veya değerlendirme daveti geldi."

            DesktopNotifier.notify(title=title, subtitle=subtitle, message=msg, sound=True)

        # 5. Persist Event
        event = EmailEvent(
            id=event_id,
            subject=subject,
            sender=sender,
            body_snippet=body_snippet[:300],
            category=category,
            matched_job_id=matched_job_id,
            matched_company=matched_company,
            confidence=confidence,
            action_taken=action_taken,
        )
        self.storage.save_email_event(event)
        return event

    def process_mock_inbox(self, mock_emails: List[Dict[str, str]]) -> List[EmailEvent]:
        """Processes a batch of raw or mock emails."""
        events = []
        for em in mock_emails:
            event = self.triage_email(
                subject=em.get("subject", ""),
                sender=em.get("sender", ""),
                body=em.get("body", ""),
                message_id=em.get("id"),
            )
            events.append(event)
        return events

    def sync_imap_inbox(
        self,
        host: str,
        username: str,
        password: str,
        folder: str = "INBOX",
        limit: int = 15,
        port: int = 993,
    ) -> List[EmailEvent]:
        """
        Connects securely to user's IMAP inbox, fetches recent unread emails,
        and triages them locally without sharing any data externally.
        """
        events = []
        try:
            mail = imaplib.IMAP4_SSL(host, port)
            mail.login(username, password)
            mail.select(folder, readonly=True)

            status, search_data = mail.search(None, 'UNSEEN')
            msg_ids = search_data[0].split()
            if not msg_ids:
                # If no unread, check recent messages
                status, search_data = mail.search(None, 'ALL')
                msg_ids = search_data[0].split()[-limit:]

            for m_id in msg_ids[-limit:]:
                status, data = mail.fetch(m_id, "(RFC822)")
                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = clean_header_str(msg.get("Subject"))
                        sender = clean_header_str(msg.get("From"))

                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body = payload.decode(errors="replace")
                                        break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body = payload.decode(errors="replace")

                        event = self.triage_email(
                            subject=subject,
                            sender=sender,
                            body=body,
                            message_id=str(m_id),
                        )
                        events.append(event)

            mail.close()
            mail.logout()
        except Exception as e:
            logger.error(f"IMAP sync error: {e}")

        return events

    def _match_job_from_email(self, subject: str, sender: str, body: str) -> Optional[ScoredJob]:
        """Finds matching job from candidate's local brain database."""
        # 1. Search company name from sender domain (e.g. @google.com -> Google)
        sender_match = re.search(r"@([a-zA-Z0-9\-]+)\.", sender)
        if sender_match:
            domain_name = sender_match.group(1).lower()
            if domain_name not in ("gmail", "yahoo", "outlook", "hotmail", "icloud"):
                matched = self.storage.find_job_by_company(domain_name)
                if matched:
                    return matched

        # 2. Match known companies in database against subject and body
        jobs = self.storage.list_jobs(min_score=0.0)
        for j in jobs:
            comp = j.job.company.lower()
            if len(comp) > 2 and (comp in subject.lower() or comp in body.lower()):
                return j

        return None

    def _infer_company(self, sender: str, subject: str) -> str:
        sender_match = re.search(r"@([a-zA-Z0-9\-]+)\.", sender)
        if sender_match:
            dom = sender_match.group(1)
            if dom not in ("gmail", "yahoo", "outlook", "hotmail", "icloud"):
                return dom.capitalize()
        # Fallback from subject
        if " at " in subject:
            return subject.split(" at ")[-1].split()[0]
        return ""
