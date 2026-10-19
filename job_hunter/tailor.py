"""Evidence-first, deterministic CV tailoring primitives.

This MVP does not invent experience or generate prose. Add candidate evidence
from a local CV before enabling richer tailoring workflows.
"""
from __future__ import annotations

import re
from typing import Any, Dict
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting


class CVTailor:
    def __init__(self, laya_client: LayaClient):
        self.client = laya_client

    def tailor(self, profile: CandidateProfile, job: JobPosting) -> Dict[str, Any]:
        text = f"{job.title} {job.description}".casefold()
        skills = [s for s in profile.core_skills if re.search(r"\b" + re.escape(s.casefold()) + r"\b", text)]
        return {
            "job_id": job.id,
            "job_title": job.title,
            "company": job.company,
            "archetype": "evidence_only",
            "matching_skills": skills,
            "tailored_headline": profile.title,
            "tailored_summary": profile.summary,
            "tailored_bullets": [],
            "selected_projects": [],
            "cover_letter": "",
        }
