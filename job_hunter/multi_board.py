"""
Multi-Board Job Portal Scraper & Query Engine:
Supports LinkedIn, WeWorkRemotely, Wellfound, Indeed, and direct ATS boards (Greenhouse, Lever).
Integrates desktop notifications on high-scoring matches.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Callable, Dict, List, Optional
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting, ScoredJob
from job_hunter.navigator import BrowserNavigator
from job_hunter.notifier import DesktopNotifier
from job_hunter.orchestrator import JobHunterOrchestrator
from job_hunter.storage import LocalBrainStorage

logger = logging.getLogger(__name__)


class MultiBoardScraper:
    """Orchestrates job searches across multiple top job platforms."""

    PORTALS = {
        "linkedin": {
            "name": "LinkedIn",
            "build_url": lambda q, loc: f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote_plus(q)}&location={urllib.parse.quote_plus(loc)}&f_WT=2",
        },
        "wwr": {
            "name": "WeWorkRemotely",
            "build_url": lambda q, loc: f"https://weworkremotely.com/remote-jobs/search?term={urllib.parse.quote_plus(q)}",
        },
        "indeed": {
            "name": "Indeed",
            "build_url": lambda q, loc: f"https://www.indeed.com/jobs?q={urllib.parse.quote_plus(q)}&l={urllib.parse.quote_plus(loc)}&sc=0kf%3Aattr%28DSQF7%29%3B",
        },
        "wellfound": {
            "name": "Wellfound (AngelList)",
            "build_url": lambda q, loc: f"https://wellfound.com/jobs",
        },
    }

    def __init__(
        self,
        orchestrator: JobHunterOrchestrator,
        enable_notifications: bool = True,
        min_notification_score: float = 0.70,
    ):
        self.orchestrator = orchestrator
        self.enable_notifications = enable_notifications
        self.min_notification_score = min_notification_score

    def build_search_url(self, portal_key: str, keywords: str, location: str = "Remote") -> str:
        portal = self.PORTALS.get(portal_key.lower())
        if portal:
            return portal["build_url"](keywords, location)
        return keywords  # Treat as custom URL if not recognized

    def run_multi_board_hunt(
        self,
        portals: List[str],
        keywords: str,
        profile: CandidateProfile,
        max_jobs_per_portal: int = 3,
        headful: bool = False,
        on_progress: Optional[Callable[[ScoredJob], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes searches across specified portals and aggregates results.
        """
        results: Dict[str, Any] = {
            "total_discovered": 0,
            "shortlisted": 0,
            "jobs": [],
        }

        def handle_job_scored(scored: ScoredJob):
            results["total_discovered"] += 1
            if scored.status == "shortlisted":
                results["shortlisted"] += 1

            # Dispatch native desktop notification for high match
            if self.enable_notifications:
                DesktopNotifier.notify_job_match(scored, min_score_threshold=self.min_notification_score)

            if on_progress:
                on_progress(scored)

        for portal in portals:
            url = self.build_search_url(portal, keywords, location=profile.preferred_locations[0])
            logger.info(f"Starting search on {portal.upper()}: {url}")

            try:
                summary = self.orchestrator.hunt_from_browser(
                    start_url=url,
                    profile=profile,
                    max_jobs=max_jobs_per_portal,
                    headless=not headful,
                    on_progress=handle_job_scored,
                )
                results["jobs"].extend(summary.jobs)
            except Exception as e:
                logger.error(f"Error during search on {portal}: {e}")

        return results
