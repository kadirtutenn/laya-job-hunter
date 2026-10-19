"""
Local Brain Keeper: Manages local SQLite storage for discovered, scored, and validated jobs.
Adheres strictly to Local Brain Principles: 100% local, inbox isolation before promotion.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from job_hunter.models import (
    CultureReport,
    EmailEvent,
    JobPosting,
    MatchReport,
    OutreachStep,
    ScoredJob,
    ValidationResult,
)


class LocalBrainStorage:
    """Manages the local SQLite database for Job Hunter knowledge base."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to local project brain directory or current working directory
            self.db_path = Path("job_hunter_brain.db")
        else:
            self.db_path = Path(db_path)

        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                url TEXT NOT NULL,
                source TEXT,
                fit_score REAL NOT NULL,
                fit_level TEXT,
                seniority_fit TEXT,
                tech_stack_fit TEXT,
                should_apply INTEGER,
                should_apply_prob REAL,
                status TEXT NOT NULL DEFAULT 'inbox',
                is_valid INTEGER NOT NULL DEFAULT 1,
                dealbreakers TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(fit_score DESC);")

            # Level 3: Email inbox triage events
            conn.execute("""
            CREATE TABLE IF NOT EXISTS email_events (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                sender TEXT NOT NULL,
                body_snippet TEXT,
                category TEXT NOT NULL,
                matched_job_id TEXT,
                matched_company TEXT,
                confidence REAL,
                action_taken TEXT,
                received_at TEXT NOT NULL
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email_cat ON email_events(category);")

            # Level 3: Multi-touch outreach sequences
            conn.execute("""
            CREATE TABLE IF NOT EXISTS outreach_steps (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                step_day INTEGER NOT NULL,
                channel TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                scheduled_for TEXT,
                created_at TEXT NOT NULL
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outreach_job ON outreach_steps(job_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach_steps(status);")

    def exists(self, job_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,))
            return cur.fetchone() is not None

    def save(self, scored_job: ScoredJob) -> None:
        """Saves or updates a scored job."""
        data = scored_job.to_dict()
        dealbreakers_json = json.dumps(scored_job.validation.dealbreakers_triggered)
        payload_str = json.dumps(data)

        with self._get_conn() as conn:
            conn.execute("""
            INSERT INTO jobs (
                id, title, company, location, url, source,
                fit_score, fit_level, seniority_fit, tech_stack_fit,
                should_apply, should_apply_prob, status, is_valid,
                dealbreakers, payload_json, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            ON CONFLICT(id) DO UPDATE SET
                fit_score = excluded.fit_score,
                fit_level = excluded.fit_level,
                seniority_fit = excluded.seniority_fit,
                tech_stack_fit = excluded.tech_stack_fit,
                should_apply = excluded.should_apply,
                should_apply_prob = excluded.should_apply_prob,
                status = excluded.status,
                is_valid = excluded.is_valid,
                dealbreakers = excluded.dealbreakers,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """, (
                scored_job.job.id,
                scored_job.job.title,
                scored_job.job.company,
                scored_job.job.location,
                scored_job.job.url,
                scored_job.job.source,
                scored_job.match.fit_score,
                scored_job.match.fit_level,
                scored_job.match.seniority_fit,
                scored_job.match.tech_stack_fit,
                1 if scored_job.match.should_apply else 0,
                scored_job.match.should_apply_prob,
                scored_job.status,
                1 if scored_job.validation.is_valid else 0,
                dealbreakers_json,
                payload_str,
                scored_job.job.discovered_at,
                scored_job.updated_at
            ))

    def update_status(self, job_id: str, new_status: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute("SELECT payload_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return False
            payload = json.loads(row["payload_json"])
            payload["status"] = new_status
            payload["updated_at"] = datetime.now().isoformat()
            new_payload_json = json.dumps(payload)

            cur = conn.execute(
                "UPDATE jobs SET status = ?, payload_json = ?, updated_at = datetime('now') WHERE id = ?",
                (new_status, new_payload_json, job_id),
            )
            return cur.rowcount > 0

    def list_jobs(self, status: Optional[str] = None, min_score: float = 0.0) -> List[ScoredJob]:
        query = "SELECT payload_json FROM jobs WHERE fit_score >= ?"
        params: List[Any] = [min_score]

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY fit_score DESC"

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [ScoredJob.from_dict(json.loads(row["payload_json"])) for row in rows]

    def get_stats(self) -> Dict[str, int]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT status, count(*) as cnt FROM jobs GROUP BY status").fetchall()
            stats = {row["status"]: row["cnt"] for row in rows}
            total = sum(stats.values())
            stats["total"] = total
            return stats

    def get_job_by_id(self, job_id: str) -> Optional[ScoredJob]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT payload_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row:
                return ScoredJob.from_dict(json.loads(row["payload_json"]))
        return None

    def find_job_by_company(self, company_query: str) -> Optional[ScoredJob]:
        """Finds the most relevant job posting matching a company name."""
        clean_q = f"%{company_query.strip().lower()}%"
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT payload_json FROM jobs WHERE LOWER(company) LIKE ? OR ? LIKE '%' || LOWER(company) || '%' ORDER BY updated_at DESC LIMIT 1",
                (clean_q, company_query.strip().lower()),
            ).fetchone()
            if row:
                return ScoredJob.from_dict(json.loads(row["payload_json"]))
        return None

    def update_job_culture(self, job_id: str, culture: CultureReport) -> bool:
        job = self.get_job_by_id(job_id)
        if not job:
            return False
        job.culture = culture
        self.save(job)
        return True

    # --- Email Event Management ---

    def save_email_event(self, event: EmailEvent) -> None:
        with self._get_conn() as conn:
            conn.execute("""
            INSERT INTO email_events (
                id, subject, sender, body_snippet, category,
                matched_job_id, matched_company, confidence, action_taken, received_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                category = excluded.category,
                matched_job_id = excluded.matched_job_id,
                matched_company = excluded.matched_company,
                action_taken = excluded.action_taken
            """, (
                event.id,
                event.subject,
                event.sender,
                event.body_snippet,
                event.category,
                event.matched_job_id,
                event.matched_company,
                event.confidence,
                event.action_taken,
                event.received_at,
            ))

    def list_email_events(self, limit: int = 50) -> List[EmailEvent]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM email_events ORDER BY received_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [
                EmailEvent(
                    id=r["id"],
                    subject=r["subject"],
                    sender=r["sender"],
                    body_snippet=r["body_snippet"],
                    category=r["category"],
                    matched_job_id=r["matched_job_id"],
                    matched_company=r["matched_company"],
                    confidence=r["confidence"],
                    action_taken=r["action_taken"],
                    received_at=r["received_at"],
                )
                for r in rows
            ]

    # --- Outreach Sequence Management ---

    def save_outreach_step(self, step: OutreachStep) -> None:
        with self._get_conn() as conn:
            conn.execute("""
            INSERT INTO outreach_steps (
                id, job_id, step_day, channel, subject, body, status, scheduled_for, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                subject = excluded.subject,
                body = excluded.body,
                status = excluded.status,
                scheduled_for = excluded.scheduled_for
            """, (
                step.id,
                step.job_id,
                step.step_day,
                step.channel,
                step.subject,
                step.body,
                step.status,
                step.scheduled_for,
                step.created_at,
            ))

    def list_outreach_steps(
        self, job_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[OutreachStep]:
        query = "SELECT * FROM outreach_steps WHERE 1=1"
        params: List[Any] = []
        if job_id:
            query += " AND job_id = ?"
            params.append(job_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY step_day ASC, created_at ASC"

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                OutreachStep(
                    id=r["id"],
                    job_id=r["job_id"],
                    step_day=r["step_day"],
                    channel=r["channel"],
                    subject=r["subject"],
                    body=r["body"],
                    status=r["status"],
                    scheduled_for=r["scheduled_for"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def update_outreach_step(
        self,
        step_id: str,
        status: Optional[str] = None,
        body: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> bool:
        updates = []
        params = []
        if status:
            updates.append("status = ?")
            params.append(status)
        if body:
            updates.append("body = ?")
            params.append(body)
        if subject:
            updates.append("subject = ?")
            params.append(subject)

        if not updates:
            return False

        params.append(step_id)
        query = f"UPDATE outreach_steps SET {', '.join(updates)} WHERE id = ?"
        with self._get_conn() as conn:
            cur = conn.execute(query, params)
            return cur.rowcount > 0
