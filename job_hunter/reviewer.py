"""
Match Reviewer & Scorer Agent: Uses Laya decision models to evaluate candidate CV vs job posting.
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting, MatchReport

logger = logging.getLogger(__name__)


class MatchReviewer:
    """Evaluates candidate fit against job openings using Laya typed decisions."""

    def __init__(self, laya_client: LayaClient, model: str = "laya"):
        self.client = laya_client
        self.model = model

    def build_state(self, profile: CandidateProfile, job: JobPosting) -> str:
        """Constructs concise, high-signal, contrast-rich state text for Laya."""
        skills_str = ", ".join(profile.core_skills)

        return (
            f"[CANDIDATE PRIMARY EXPERTISE]:\n"
            f"- Name: {profile.name}\n"
            f"- Target Roles: {', '.join(profile.preferred_roles)}\n"
            f"- Seniority Level: Mid-Senior / Senior ({profile.min_years_experience}+ years in backend & APIs)\n"
            f"- Core Technical Stack: {skills_str}\n"
            f"- Summary: {profile.summary}\n\n"
            f"[CANDIDATE EXCLUSIONS / MISMATCH]:\n"
            f"- NOT a Native Mobile developer (No Kotlin, Android SDK, Swift, iOS)\n"
            f"- NOT a Java/Spring Boot or C# .NET developer\n"
            f"- NOT looking for Internships, Working Student, or Junior (0-1 year) roles\n"
            f"- Requires Remote or Turkey-based work authorization\n\n"
            f"[JOB OPENING]:\n"
            f"- Title: {job.title}\n"
            f"- Company: {job.company}\n"
            f"- Location: {job.location}\n"
            f"- Description & Key Requirements:\n{job.description[:2500]}"
        )

    def review(self, profile: CandidateProfile, job: JobPosting) -> MatchReport:
        """
        Runs candidate vs job comparison through Laya's decision model.
        Returns a calibrated MatchReport using direct probability distributions.
        """
        state = self.build_state(profile, job)

        questions = {
            "tech_stack_fit": {
                "type": "choice",
                "instructions": (
                    "Does the job primary daily programming language and architecture match candidate core expertise (Python/Go/FastAPI backend)?"
                ),
                "criteria": {
                    "strong_alignment": "Job primarily requires Python, Go, or backend API engineering compatible with candidate",
                    "missing_critical": "Job primarily requires a different domain (Native Android Kotlin, iOS Swift, Java Spring, C++, Embedded, or Frontend-only)",
                },
            },
            "seniority_fit": {
                "type": "choice",
                "instructions": "Is the role seniority level compatible with a 3+ years Mid-Senior engineer?",
                "criteria": {
                    "level_matched": "Role is Mid, Senior, or standard Software Engineer suitable for candidate",
                    "level_mismatch": "Role is Intern, Working Student, Junior (0-1 yr), or VP/Director",
                },
            },
            "should_apply": {
                "type": "noul",
                "instructions": "Considering candidate background and the job requirements, is this position recommended for the candidate to apply to?",
            },
        }

        try:
            resp = self.client.decide(state=state, questions=questions, model=self.model)
            answers = resp.get("answers", {})

            # Probabilities extraction
            tech_prob = float(answers.get("tech_stack_fit", {}).get("probabilities", {}).get("strong_alignment", 0.5))
            seniority_prob = float(answers.get("seniority_fit", {}).get("probabilities", {}).get("level_matched", 0.5))
            should_apply_prob = float(answers.get("should_apply", {}).get("noul", 0.5))

            # Calibrated composite match percentage (0.0 to 1.0)
            fit_pct = (0.55 * tech_prob) + (0.25 * seniority_prob) + (0.20 * should_apply_prob)
            fit_pct = min(1.0, max(0.0, fit_pct))

            seniority = answers.get("seniority_fit", {}).get("choice", "level_matched")
            tech_stack = answers.get("tech_stack_fit", {}).get("choice", "strong_alignment" if tech_prob >= 0.5 else "missing_critical")

            if fit_pct >= 0.70:
                fit_level = "perfect"
            elif fit_pct >= 0.50:
                fit_level = "strong"
            elif fit_pct >= 0.30:
                fit_level = "partial"
            else:
                fit_level = "poor"

            should_apply = bool(should_apply_prob >= 0.50 and fit_pct >= 0.48 and seniority != "level_mismatch")
            confidence = float(answers.get("tech_stack_fit", {}).get("confidence", 0.5))

            return MatchReport(
                fit_score=round(fit_pct, 4),
                fit_level=fit_level,
                seniority_fit=seniority,
                tech_stack_fit=tech_stack,
                should_apply=should_apply,
                should_apply_prob=round(should_apply_prob, 4),
                confidence=round(confidence, 4),
                details=answers,
            )
        except Exception as e:
            logger.error(f"Laya match review failed: {e}")
            return MatchReport(
                fit_score=0.5,
                fit_level="partial",
                seniority_fit="level_matched",
                tech_stack_fit="partial_overlap",
                should_apply=False,
                should_apply_prob=0.5,
                confidence=0.0,
                details={"error": str(e)},
            )
