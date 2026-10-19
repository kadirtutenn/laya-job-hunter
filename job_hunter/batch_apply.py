"""
Automatic Application Approval Queue:
Prepares shortlisted application forms for user review without submitting them.
Generates tailored ATS PDF resumes, fills multi-step application forms with Playwright,
uploads resumes, updates job statuses to 'applied', and initializes outreach sequences.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from job_hunter.easy_apply import EasyApplyAgent
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting, ScoredJob
from job_hunter.navigator import DEFAULT_CHROME_PROFILE_DIR
from job_hunter.notifier import DesktopNotifier
from job_hunter.pdf_generator import PDFResumeGenerator
from job_hunter.storage import LocalBrainStorage
from job_hunter.tailor import CVTailor

logger = logging.getLogger(__name__)


@dataclass
class BatchApplyResult:
    total_requested: int
    prepared_count: int
    failed_count: int
    results: List[Dict[str, Any]] = field(default_factory=list)


class BatchApplyOrchestrator:
    """Prepares application forms for review; this tool never submits applications."""

    def __init__(
        self,
        laya_client: LayaClient,
        storage: LocalBrainStorage,
        user_data_dir: Optional[str] = None,
    ):
        self.client = laya_client
        self.storage = storage
        self.user_data_dir = user_data_dir or DEFAULT_CHROME_PROFILE_DIR
        self.tailor = CVTailor(self.client)
        self.pdf_generator = PDFResumeGenerator()
        self.easy_apply = EasyApplyAgent(laya_client=laya_client, auto_submit=False)

    def execute_batch_apply(
        self,
        profile: CandidateProfile,
        job_ids: Optional[List[str]] = None,
        limit: int = 5,
        headful: bool = True,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> BatchApplyResult:
        """
        Fills application forms for review and leaves submission to the user.
        """
        # 1. Collect target jobs
        target_jobs: List[ScoredJob] = []
        if job_ids:
            for jid in job_ids:
                j = self.storage.get_job_by_id(jid)
                if j:
                    if j.status == "applied":
                        logger.warning(f"İlan zaten başvurulmuş, atlanıyor: {j.job.title} @ {j.job.company} (ID: {j.job.id})")
                        continue
                    target_jobs.append(j)
        else:
            # Pick strictly from shortlisted jobs (excluding applied)
            target_jobs = self.storage.list_jobs(status="shortlisted")[:limit]

        if not target_jobs:
            logger.info("No unapplied shortlisted jobs found for batch application.")
            return BatchApplyResult(total_requested=0, prepared_count=0, failed_count=0)

        from playwright.sync_api import sync_playwright

        failed = 0
        execution_details = []

        logger.info(f"Preparing {len(target_jobs)} application forms for user review...")

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=not headful,
                viewport={"width": 1280, "height": 850},
                args=[],
            )
            page = context.new_page()

            for idx, scored in enumerate(target_jobs):
                job = scored.job
                job_title_short = f"{job.title} @ {job.company}"
                logger.info(f"[{idx+1}/{len(target_jobs)}] Processing: {job_title_short}")

                if on_progress:
                    on_progress({
                        "step": "starting",
                        "current": idx + 1,
                        "total": len(target_jobs),
                        "job_id": job.id,
                        "title": job_title_short,
                    })

                try:
                    # 1. Generate tailored ATS PDF
                    tailored_data = self.tailor.tailor(profile, job)
                    pdf_path = self.pdf_generator.generate(profile, job, tailored_data)

                    # 2. Navigate to Job URL
                    page.goto(job.url, wait_until="domcontentloaded", timeout=25000)
                    time.sleep(2.0)

                    # 3. Detect and click Easy Apply / Apply button
                    apply_btn = page.query_selector(
                        '.jobs-apply-button, button:has-text("Easy Apply"), button:has-text("Kolay Başvuru"), a:has-text("Apply")'
                    )

                    if apply_btn and apply_btn.is_visible():
                        apply_btn.click()
                        time.sleep(2.0)

                        # 4. Fill form with EasyApplyAgent
                        fill_report = self.easy_apply.fill_form_step(
                            page=page,
                            profile=profile,
                            resume_pdf_path=str(pdf_path),
                        )

                        # Leave the final review and submit action to the user.
                        self.storage.update_status(job.id, "shortlisted")

                        res_item = {
                            "job_id": job.id,
                            "title": job.title,
                            "company": job.company,
                            "status": "prepared_for_review",
                            "fields_filled": len(fill_report.get("filled_fields", [])),
                            "questions_answered": len(fill_report.get("answered_questions", [])),
                            "pdf_resume": str(pdf_path),
                        }
                        execution_details.append(res_item)

                        if on_progress:
                            on_progress({
                                "step": "completed",
                                "current": idx + 1,
                                "total": len(target_jobs),
                                "job_id": job.id,
                                "result": res_item,
                            })

                        # Respectful fixed pacing; this does not guarantee platform access.
                        time.sleep(3.0)
                    else:
                        logger.warning(f"No direct Easy Apply button found for: {job.title}")
                        # Mark as shortlisted with manual action note
                        self.storage.update_status(job.id, "shortlisted")
                        failed += 1
                        execution_details.append({
                            "job_id": job.id,
                            "title": job.title,
                            "company": job.company,
                            "status": "requires_manual_click",
                            "error": "No direct apply button detected",
                        })

                except Exception as e:
                    logger.error(f"Error applying to {job.title}: {e}")
                    failed += 1
                    execution_details.append({
                        "job_id": job.id,
                        "title": job.title,
                        "company": job.company,
                        "status": "failed",
                        "error": str(e),
                    })

            context.close()

        # Send summary notification
        if execution_details:
            DesktopNotifier.notify(
                title="Başvuru taslakları hazır",
                subtitle="Son inceleme ve gönderim kullanıcıya ait",
                message=f"{len(execution_details)} ilan işlendi; hiçbir başvuru otomatik gönderilmedi.",
                sound=False,
            )

        return BatchApplyResult(
            total_requested=len(target_jobs),
            prepared_count=sum(1 for item in execution_details if item.get("status") == "prepared_for_review"),
            failed_count=failed,
            results=execution_details,
        )
