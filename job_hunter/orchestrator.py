"""
Orchestrator Agent: Coordinates Navigator, Extractor, Reviewer, Validator, and Local Brain Storage.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, List, Optional
from job_hunter.extractor import JobExtractor
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting, ScoredJob
from job_hunter.navigator import BrowserNavigator
from job_hunter.reviewer import MatchReviewer
from job_hunter.storage import LocalBrainStorage
from job_hunter.validator import JobValidator

logger = logging.getLogger(__name__)


@dataclass
class HuntSummary:
    discovered: int = 0
    inbox: int = 0
    shortlisted: int = 0
    archived: int = 0
    skipped_duplicates: int = 0
    jobs: List[ScoredJob] = None

    def __post_init__(self):
        if self.jobs is None:
            self.jobs = []


class JobHunterOrchestrator:
    """End-to-end multi-agent orchestrator."""

    def __init__(
        self,
        laya_client: Optional[LayaClient] = None,
        storage: Optional[LocalBrainStorage] = None,
        min_fit_threshold: float = 0.50,
        model: str = "laya",
    ):
        self.client = laya_client or LayaClient()
        self.storage = storage or LocalBrainStorage()
        self.reviewer = MatchReviewer(self.client, model=model)
        self.validator = JobValidator(min_fit_threshold=min_fit_threshold)

    def process_job(
        self, profile: CandidateProfile, job: JobPosting
    ) -> Optional[ScoredJob]:
        """Runs single job through Reviewer -> Validator -> Local Brain Keeper."""
        if self.storage.exists(job.id):
            logger.info(f"Job '{job.title}' at {job.company} already in brain, skipping.")
            return None

        # 1. Reviewer (Laya Engine)
        match_report = self.reviewer.review(profile, job)

        # 2. Validator & Guard
        val_result = self.validator.validate(profile, job, match_report)

        # 3. Determine status according to Local Brain principles
        if not val_result.is_valid:
            status = "archived"
        elif match_report.fit_score >= 0.70:
            status = "shortlisted"
        else:
            status = "inbox"

        scored_job = ScoredJob(
            job=job,
            match=match_report,
            validation=val_result,
            status=status,
        )

        # 4. Save to Local Brain
        self.storage.save(scored_job)
        return scored_job

    def hunt_from_browser(
        self,
        start_url: str,
        profile: CandidateProfile,
        max_jobs: int = 10,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
        on_progress: Optional[Callable[[ScoredJob], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> HuntSummary:
        """Launches autonomous browser navigation and processes all found jobs."""
        summary = HuntSummary()
        navigator = BrowserNavigator(
            self.client,
            headless=headless,
            max_steps=25,
            user_data_dir=user_data_dir,
        )

        def emit(msg: str):
            if on_log:
                try:
                    on_log(msg)
                except Exception:
                    pass

        def handle_job(job: JobPosting):
            handle_batch([job])

        def handle_batch(jobs: List[JobPosting]):
            if not jobs:
                return

            companies = [j.company for j in jobs]
            emit(f"🤖 [Laya Batch] {len(jobs)} ilan eşzamanlı analiz ediliyor: {', '.join(companies)}...")

            def evaluate_single(j: JobPosting):
                summary.discovered += 1
                return self.process_job(profile, j), j

            with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
                eval_results = list(pool.map(evaluate_single, jobs))

            for scored, job in eval_results:
                if scored is None:
                    summary.skipped_duplicates += 1
                    emit(f"⏩ [Mükerrer] '{job.title}' @ {job.company} geçildi.")
                else:
                    summary.jobs.append(scored)
                    score_pct = int(round(scored.match.fit_score * 100))
                    recommendation = "EVET" if scored.match.should_apply else "HAYIR"
                    emit(f"🎯 [Laya Skoru] %{score_pct} ({scored.status.upper()}) | {job.title} @ {job.company} (Başvuru: {recommendation})")
                    if scored.status == "shortlisted":
                        summary.shortlisted += 1
                    elif scored.status == "inbox":
                        summary.inbox += 1
                    else:
                        summary.archived += 1
                        if scored.validation.dealbreakers_triggered:
                            emit(f"⚠️ [Elendi] {job.company}: {', '.join(scored.validation.dealbreakers_triggered)}")

                    if on_progress:
                        on_progress(scored)

        navigator.navigate_and_harvest(
            start_url=start_url,
            profile=profile,
            on_job_found=handle_job,
            on_batch_found=handle_batch,
            on_log=on_log,
            max_jobs=max_jobs,
            should_stop=should_stop,
        )

        return summary

    def process_job_batch(
        self,
        jobs: List[JobPosting],
        profile: CandidateProfile,
        on_progress: Optional[Callable[[ScoredJob], None]] = None,
    ) -> HuntSummary:
        """Processes a list of raw JobPosting objects directly."""
        summary = HuntSummary()

        for job in jobs:
            summary.discovered += 1
            scored = self.process_job(profile, job)
            if scored is None:
                summary.skipped_duplicates += 1
            else:
                summary.jobs.append(scored)
                if scored.status == "shortlisted":
                    summary.shortlisted += 1
                elif scored.status == "inbox":
                    summary.inbox += 1
                else:
                    summary.archived += 1

                if on_progress:
                    on_progress(scored)

        return summary
