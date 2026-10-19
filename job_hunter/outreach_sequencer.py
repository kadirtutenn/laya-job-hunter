"""
Multi-Touch Outreach Sequencer:
Generates automated 3-stage follow-up sequences (Day 0, Day 5, Day 12)
for shortlisted jobs, providing candidate review & approval before sending.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from job_hunter.models import CandidateProfile, JobPosting, OutreachStep, ScoredJob
from job_hunter.storage import LocalBrainStorage

logger = logging.getLogger(__name__)


class OutreachSequencer:
    """Creates and manages multi-touch outreach campaigns for target job applications."""

    def __init__(self, storage: LocalBrainStorage):
        self.storage = storage

    def generate_sequence(
        self, profile: CandidateProfile, job: JobPosting
    ) -> List[OutreachStep]:
        """
        Creates Day 0, Day 5, and Day 12 outreach steps tailored to the job opening.
        Persists generated drafts to local brain storage.
        """
        today = datetime.now()
        company_tag = job.company if job.company and job.company != "Tech Company" else "your team"
        primary_skill = profile.core_skills[0] if profile.core_skills else "Python"
        secondary_skills = ", ".join(profile.core_skills[1:3]) if len(profile.core_skills) > 1 else "Distributed Systems"

        steps: List[OutreachStep] = []

        # ---------------------------------------------------------------------
        # Step 1: Day 0 - Initial LinkedIn Note (< 300 chars)
        # ---------------------------------------------------------------------
        li_note = (
            f"Hi! Noticed the {job.title} role at {company_tag}. "
            f"With {profile.min_years_experience}+ yrs in {primary_skill} & {secondary_skills}, "
            f"I've built similar resilient architectures and would love to connect!"
        )
        if len(li_note) > 295:
            li_note = li_note[:292] + "..."

        step_0_li_id = hashlib.sha256(f"{job.id}:step0_li".encode("utf-8")).hexdigest()[:16]
        step_0_li = OutreachStep(
            id=step_0_li_id,
            job_id=job.id,
            step_day=0,
            channel="linkedin",
            subject=f"LinkedIn Connection: {job.title}",
            body=li_note,
            status="draft",
            scheduled_for=today.strftime("%Y-%m-%d"),
        )
        steps.append(step_0_li)

        # ---------------------------------------------------------------------
        # Step 2: Day 0 - Hiring Manager Cold Outreach Email
        # ---------------------------------------------------------------------
        cold_email_body = (
            f"Subject: Application & Inquiry: {job.title} – {profile.name}\n\n"
            f"Hi Hiring Team at {job.company},\n\n"
            f"I recently submitted my application for the {job.title} position at {job.company}. "
            f"Given my background with {profile.min_years_experience}+ years architecting high-scale backends and "
            f"decision pipelines using {primary_skill} and {secondary_skills}, I believe my experience directly aligns "
            f"with your engineering initiatives.\n\n"
            f"I have attached my tailored ATS resume for your convenience. I would welcome a brief conversation "
            f"to share how I can immediately add value to your team.\n\n"
            f"Best regards,\n"
            f"{profile.name}\n"
            f"{profile.email} | {profile.phone}\n"
            f"{profile.linkedin_url} | {profile.portfolio_url}"
        )
        step_0_email_id = hashlib.sha256(f"{job.id}:step0_email".encode("utf-8")).hexdigest()[:16]
        step_0_email = OutreachStep(
            id=step_0_email_id,
            job_id=job.id,
            step_day=0,
            channel="email",
            subject=f"Application: {job.title} – {profile.name}",
            body=cold_email_body,
            status="draft",
            scheduled_for=today.strftime("%Y-%m-%d"),
        )
        steps.append(step_0_email)

        # ---------------------------------------------------------------------
        # Step 3: Day 5 - Gentle Follow-Up Email
        # ---------------------------------------------------------------------
        day_5_date = today + timedelta(days=5)
        followup_body = (
            f"Hi Hiring Team at {job.company},\n\n"
            f"I wanted to follow up briefly on my application for the {job.title} role submitted earlier this week. "
            f"I understand your schedule is busy, but I remain enthusiastic about the opportunity to contribute to {job.company}.\n\n"
            f"In a recent production architecture, I led a migration that improved throughput by 3x while cutting latency in half "
            f"using {primary_skill} and asynchronous worker pools. I would love the chance to bring that same engineering rigor to your team.\n\n"
            f"Please let me know if you need any additional portfolio samples or code references.\n\n"
            f"Best regards,\n"
            f"{profile.name}"
        )
        step_5_id = hashlib.sha256(f"{job.id}:step5".encode("utf-8")).hexdigest()[:16]
        step_5 = OutreachStep(
            id=step_5_id,
            job_id=job.id,
            step_day=5,
            channel="email",
            subject=f"Following up: {job.title} application – {profile.name}",
            body=followup_body,
            status="draft",
            scheduled_for=day_5_date.strftime("%Y-%m-%d"),
        )
        steps.append(step_5)

        # ---------------------------------------------------------------------
        # Step 4: Day 12 - Value-Add Touchpoint Email
        # ---------------------------------------------------------------------
        day_12_date = today + timedelta(days=12)
        value_add_body = (
            f"Hi Team at {job.company},\n\n"
            f"I came across some recent engineering challenges regarding scaling distributed services and automated agents, "
            f"and it immediately made me think of {job.company}'s work with {job.title}.\n\n"
            f"I put together a quick technical breakdown demonstrating how deterministic perception with calibrated decision heads "
            f"can solve reliability bottlenecks without prohibitive cloud API overhead. You can review my open-source work at:\n"
            f"{profile.github_url}\n\n"
            f"Whether or not the timing is right for this specific role, I would enjoy staying in touch and exchanging ideas on modern architecture.\n\n"
            f"Warm regards,\n"
            f"{profile.name}\n"
            f"{profile.linkedin_url}"
        )
        step_12_id = hashlib.sha256(f"{job.id}:step12".encode("utf-8")).hexdigest()[:16]
        step_12 = OutreachStep(
            id=step_12_id,
            job_id=job.id,
            step_day=12,
            channel="email",
            subject=f"Engineering Thoughts & Follow-up for {job.company} – {profile.name}",
            body=value_add_body,
            status="draft",
            scheduled_for=day_12_date.strftime("%Y-%m-%d"),
        )
        steps.append(step_12)

        # Save all steps to storage
        for s in steps:
            self.storage.save_outreach_step(s)

        return steps

    def get_job_sequence(self, job_id: str) -> List[OutreachStep]:
        return self.storage.list_outreach_steps(job_id=job_id)

    def get_review_queue(self, status: Optional[str] = "draft") -> List[OutreachStep]:
        """Returns all outreach steps currently awaiting candidate review or approval."""
        return self.storage.list_outreach_steps(status=status)

    def approve_step(self, step_id: str) -> bool:
        """Approves a draft outreach step for transmission."""
        return self.storage.update_outreach_step(step_id, status="approved")

    def mark_sent(self, step_id: str) -> bool:
        """Marks an outreach step as sent."""
        return self.storage.update_outreach_step(step_id, status="sent")

    def update_draft(self, step_id: str, subject: str, body: str) -> bool:
        """Allows candidate to edit outreach content before sending."""
        return self.storage.update_outreach_step(step_id, subject=subject, body=body)
