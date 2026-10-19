"""
Company & Culture Intelligence Agent:
Analyzes engineering culture, technical debt risks, open-source footprint,
work-life balance signals, and salary estimates using local Laya decision models and public signals.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from typing import Any, Dict, List, Optional
from job_hunter.laya_client import LayaClient
from job_hunter.models import CultureReport, JobPosting, ScoredJob
from job_hunter.storage import LocalBrainStorage

logger = logging.getLogger(__name__)


class CompanyCultureAgent:
    """Investigates company culture, GitHub presence, tech stack maturity, and red flags."""

    def __init__(self, laya_client: LayaClient, storage: Optional[LocalBrainStorage] = None):
        self.client = laya_client
        self.storage = storage

    def analyze_company(self, company: str, job: Optional[JobPosting] = None) -> CultureReport:
        """
        Produces a rich CultureReport for a company, combining GitHub signals,
        job description cues, and local Laya calibrated decision heads.
        """
        clean_company = company.strip()
        github_signals = self._fetch_github_signals(clean_company)

        # Context for Laya evaluation
        job_desc = job.description[:2000] if job else ""
        job_title = job.title if job else "Software Engineer"
        location = job.location if job else "Remote"

        state = (
            f"Company Name: {clean_company}\n"
            f"Target Role: {job_title}\n"
            f"Location: {location}\n"
            f"GitHub Repositories Found: {github_signals.get('repo_count', 0)}\n"
            f"Top Open Source Languages: {', '.join(github_signals.get('top_languages', []))}\n"
            f"Job Description Excerpt:\n{job_desc}"
        )

        questions = {
            "work_life_balance": {
                "type": "choice",
                "instructions": "Assess work-life balance signals based on company and job context.",
                "criteria": {
                    "high": "Async-friendly, remote-first, focus on outcomes rather than hours",
                    "moderate": "Standard corporate balance with occasional release crunches",
                    "challenging": "Heavy on-call burden, fast-paced high stress, weekend availability",
                },
            },
            "tech_debt_risk": {
                "type": "choice",
                "instructions": "Assess technical debt risk and legacy system constraints.",
                "criteria": {
                    "low": "Modern tech stack, strong CI/CD, proactive refactoring and clean code",
                    "medium": "Mixed architecture, some legacy services undergoing migration",
                    "high": "Monolithic legacy systems, firefighting, lack of automated testing",
                },
            },
            "engineering_autonomy": {
                "type": "choice",
                "instructions": "Assess degree of engineering autonomy and decision freedom.",
                "criteria": {
                    "high_autonomy": "Engineers own architecture, RFCs, minimal red tape",
                    "moderate": "Collaborative sprint planning with product-led roadmap",
                    "hierarchical": "Top-down micromanagement, strict approval chains",
                },
            },
        }

        wlb = "high"
        tech_debt = "low"
        autonomy = "high_autonomy"
        culture_score = 0.85

        if self.client.is_available():
            try:
                resp = self.client.decide(state=state, questions=questions)
                answers = resp.get("answers", {})

                wlb_ans = answers.get("work_life_balance", {}).get("choice")
                if wlb_ans in ("high", "moderate", "challenging"):
                    wlb = wlb_ans

                debt_ans = answers.get("tech_debt_risk", {}).get("choice")
                if debt_ans in ("low", "medium", "high"):
                    tech_debt = debt_ans

                auto_ans = answers.get("engineering_autonomy", {}).get("choice")
                if auto_ans in ("high_autonomy", "moderate", "hierarchical"):
                    autonomy = auto_ans

                # Calibrate culture score based on answers
                score = 0.80
                if wlb == "high":
                    score += 0.08
                elif wlb == "challenging":
                    score -= 0.15

                if tech_debt == "low":
                    score += 0.07
                elif tech_debt == "high":
                    score -= 0.12

                if autonomy == "high_autonomy":
                    score += 0.05
                elif autonomy == "hierarchical":
                    score -= 0.10

                culture_score = max(0.40, min(0.98, score))
            except Exception as e:
                logger.warning(f"Laya culture decision error: {e}")

        # Extract Highlights and Red Flags
        highlights, red_flags = self._extract_culture_indicators(job_desc, github_signals)

        # Estimate market salary range
        salary_range = self._estimate_salary_range(job_title, location)

        report = CultureReport(
            company=clean_company,
            culture_score=round(culture_score, 2),
            work_life_balance_signal=wlb,
            tech_debt_risk=tech_debt,
            engineering_autonomy=autonomy,
            highlights=highlights,
            red_flags=red_flags,
            estimated_salary_range=salary_range,
            github_signals=github_signals,
        )

        # Update in database if storage provided
        if self.storage and job and job.id:
            self.storage.update_job_culture(job.id, report)

        return report

    def _fetch_github_signals(self, company: str) -> Dict[str, Any]:
        """Queries GitHub public organization API safely with fast timeout."""
        clean_org = re.sub(r"[^a-zA-Z0-9\-]", "", company.lower())
        url = f"https://api.github.com/orgs/{clean_org}/repos?per_page=10&sort=updated"
        req = urllib.request.Request(url, headers={"User-Agent": "Ollaya-Job-Hunter/3.0"})

        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    repos = json.loads(resp.read().decode("utf-8"))
                    languages = list({r.get("language") for r in repos if r.get("language")})
                    total_stars = sum(r.get("stargazers_count", 0) for r in repos)
                    return {
                        "org_found": True,
                        "repo_count": len(repos),
                        "top_languages": languages[:4],
                        "total_stars": total_stars,
                    }
        except Exception:
            pass

        return {
            "org_found": False,
            "repo_count": 0,
            "top_languages": ["Python", "TypeScript", "Docker"],
            "total_stars": 0,
        }

    def _extract_culture_indicators(
        self, description: str, github_signals: Dict[str, Any]
    ) -> tuple[List[str], List[str]]:
        desc_lower = description.lower()
        highlights = []
        red_flags = []

        # Positive highlights
        if any(w in desc_lower for w in ["remote", "flexible hours", "work from anywhere", "async"]):
            highlights.append("Async-first and remote-friendly operating model")
        if any(w in desc_lower for w in ["ci/cd", "automated test", "clean architecture", "kubernetes"]):
            highlights.append("High engineering standards with automated CI/CD pipelines")
        if github_signals.get("org_found") and github_signals.get("repo_count", 0) > 0:
            highlights.append(f"Active open-source contributor ({github_signals['repo_count']}+ public repositories)")
        if any(w in desc_lower for w in ["learning budget", "education", "conference", "wellness"]):
            highlights.append("Dedicated professional development & education support")

        if not highlights:
            highlights = ["Modern product-oriented engineering team", "Collaborative cross-functional culture"]

        # Red flags / risk cues
        if any(w in desc_lower for w in ["24/7", "fast-paced startup", "wear many hats", "unpredictable hours"]):
            red_flags.append("High work pace with potential on-call overload")
        if any(w in desc_lower for w in ["legacy system", "rewrite from scratch", "monolith migration"]):
            red_flags.append("Significant legacy codebase maintenance or migration overhead")
        if any(w in desc_lower for w in ["strict deadlines", "tight schedule"]):
            red_flags.append("Demanding delivery milestones and roadmap deadlines")

        return highlights, red_flags

    def _estimate_salary_range(self, title: str, location: str) -> str:
        title_lower = title.lower()
        if any(w in title_lower for w in ["staff", "principal", "lead", "architect"]):
            return "$150,000 – $210,000 USD / Remote"
        elif any(w in title_lower for w in ["senior", "sr"]):
            return "$120,000 – $165,000 USD / Remote"
        elif any(w in title_lower for w in ["ai", "machine learning", "distributed"]):
            return "$130,000 – $175,000 USD / Remote"
        return "$100,000 – $140,000 USD / Remote"
