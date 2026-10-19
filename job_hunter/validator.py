"""
Validator & Guard Agent: Verifies dealbreakers, location compliance, spam signals, and thresholds.
"""

from __future__ import annotations

import re
from typing import List
from job_hunter.models import CandidateProfile, JobPosting, MatchReport, ValidationResult


class JobValidator:
    """Quality and compliance guard for job postings."""

    def __init__(self, min_fit_threshold: float = 0.50):
        self.min_fit_threshold = min_fit_threshold

    def validate(
        self, profile: CandidateProfile, job: JobPosting, match: MatchReport
    ) -> ValidationResult:
        reasons: List[str] = []
        dealbreakers: List[str] = []
        full_text = f"{job.title} {job.company} {job.location} {job.description}".lower()

        # 1. Check candidate dealbreakers (regex and semantic patterns)
        for dealbreaker in profile.dealbreakers:
            db_clean = dealbreaker.lower()
            if "citizenship" in db_clean:
                if re.search(r"\b(us\s*citizen|united\s*states\s*citizen|citizenship\s*required)\b", full_text):
                    dealbreakers.append("US Citizenship Required")
            elif "security clearance" in db_clean or "clearance" in db_clean:
                if re.search(r"\b(security\s*clearance|top\s*secret|active\s*clearance)\b", full_text):
                    dealbreakers.append("Security Clearance Required")
            elif "unpaid" in db_clean or "internship" in db_clean:
                if re.search(r"\b(unpaid|volunteer|for\s*college\s*credit)\b", full_text):
                    dealbreakers.append("Unpaid Position")
            else:
                pattern = re.escape(db_clean)
                if re.search(pattern, full_text):
                    dealbreakers.append(dealbreaker)

        # 2. Check common red flags & scam indicators
        spam_patterns = [
            r"pay to apply",
            r"send money via wire",
            r"crypto transfer required",
            r"buy your own equipment from our vendor",
            r"unpaid commission only",
        ]
        for sp in spam_patterns:
            if re.search(sp, full_text):
                dealbreakers.append(f"Spam indicator detected: '{sp}'")

        # 3. Check description length / quality
        if len(job.description.strip()) < 80:
            reasons.append("Suspiciously brief or empty job description.")

        # 4. Check location compatibility
        is_remote_wanted = any("remote" in loc.lower() for loc in profile.preferred_locations)
        if is_remote_wanted:
            # If candidate wants remote, check if job explicitly requires full-time onsite in another region
            if re.search(r"\b(strictly\s*onsite|onsite\s*only|100%\s*on-site|must\s*be\s*in\s*office\s*5\s*days)\b", full_text):
                dealbreakers.append("Strictly Onsite Requirement (Conflicts with Remote Preference)")

        # 5. Seniority mismatch check from Laya
        if match.seniority_fit == "level_mismatch":
            reasons.append("Seniority level mismatch (Junior/Intern or inappropriate level).")

        # 6. Fit score threshold check
        if match.fit_score < self.min_fit_threshold and not match.should_apply:
            reasons.append(
                f"Fit score ({match.fit_score * 100:.1f}%) is below minimum threshold ({self.min_fit_threshold * 100:.1f}%)."
            )

        is_valid = len(dealbreakers) == 0 and len(reasons) == 0

        if is_valid:
            reasons.append("All quality, location, and fit threshold checks passed.")

        return ValidationResult(
            is_valid=is_valid,
            reasons=reasons,
            dealbreakers_triggered=dealbreakers,
        )
