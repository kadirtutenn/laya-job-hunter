"""
Interview Prep & Recruiter Outreach Assistant:
Generates targeted technical/behavioral interview questions and personalized outreach messages.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting


class InterviewPrepAssistant:
    """Prepares interview questions, talking points, and outreach notes for candidates."""

    def __init__(self, laya_client: LayaClient):
        self.client = laya_client

    def generate_prep_kit(self, profile: CandidateProfile, job: JobPosting) -> Dict[str, Any]:
        """
        Creates an end-to-end interview prep kit and outreach pack tailored to the job opening.
        """
        job_lower = f"{job.title} {job.description}".lower()

        # Identify primary technical themes
        themes = []
        if any(w in job_lower for w in ["python", "fastapi", "asyncio", "django"]):
            themes.append("Python & Async Ecosystem")
        if any(w in job_lower for w in ["rust", "memory", "concurrency"]):
            themes.append("Rust Systems & Performance")
        if any(w in job_lower for w in ["distributed", "raft", "kafka", "scalab"]):
            themes.append("Distributed Systems & Data Consistency")
        if any(w in job_lower for w in ["agent", "llm", "decision", "ai", "model"]):
            themes.append("AI Agents & Decision Pipelines")
        if any(w in job_lower for w in ["playwright", "automation", "scraping", "browser"]):
            themes.append("Browser Automation & DOM Perception")
        if any(w in job_lower for w in ["postgres", "sql", "database"]):
            themes.append("Database Optimization & Indexing")

        if not themes:
            themes = ["High-Scale Backend Architecture", "API Design & Resiliency"]

        primary_theme = themes[0]

        # 1. Technical Questions & Talking Points
        technical_questions = [
            {
                "question": f"How do you design and structure high-throughput workloads in {primary_theme}?",
                "talking_points": (
                    f"Highlight your experience with async non-blocking I/O, worker queues, and backpressure handling. "
                    f"Mention concrete metrics from your {profile.min_years_experience}+ years scaling backend services."
                ),
            },
            {
                "question": f"What strategies do you use for fault tolerance, retries, and data consistency in {job.company}'s domain?",
                "talking_points": (
                    "Discuss idempotency keys, circuit breakers, exponential backoff with jitter, and dead letter queues. "
                    "Emphasize decoupling services via event-driven messaging."
                ),
            },
            {
                "question": f"How do you monitor, profile, and optimize performance bottlenecks in production?",
                "talking_points": (
                    "Explain your approach to structured telemetry (OpenTelemetry, Prometheus), flame graphs, "
                    "and query latency analysis in PostgreSQL / distributed stores."
                ),
            },
            {
                "question": f"When integrating AI decision models or automation pipelines, how do you handle hallucinations or timeouts?",
                "talking_points": (
                    "Share how you prefer deterministic DOM perception and calibrated decision heads (like Laya) "
                    "over slow, expensive free-text LLMs for sub-second, reliable automation."
                ),
            },
            {
                "question": f"How do you balance fast iteration with rigorous testing in high-stakes environments?",
                "talking_points": (
                    "Discuss test pyramids, hermetic integration tests, contract testing, and CI/CD pipelines. "
                    "Mention zero-downtime blue/green or canary deployments."
                ),
            },
        ]

        # 2. Behavioral / STAR Questions
        behavioral_questions = [
            {
                "question": "Tell me about a time you had a strong technical disagreement regarding system architecture.",
                "guide": "Situation: Legacy service rewrite vs incremental refactor. Task: Align team on trade-offs. Action: Built quick proof-of-concept benchmarks. Result: Saved 3 months of refactoring with clear consensus.",
            },
            {
                "question": f"Describe a high-pressure production incident you led and resolved.",
                "guide": "Focus on calm diagnosis, blameless post-mortem, root cause mitigation rather than symptomatic patching.",
            },
            {
                "question": "How do you mentor engineers and elevate engineering standards across the organization?",
                "guide": "Highlight code review principles (Lazy Senior Developer / simplicity first), automated linting, and architecture design docs (RFCs).",
            },
        ]

        # 3. Personalized LinkedIn Connection Note (< 300 chars)
        company_tag = job.company if job.company and job.company != "Tech Company" else "your team"
        connection_note = (
            f"Hi! Noticed the {job.title} role at {company_tag}. "
            f"With {profile.min_years_experience}+ yrs in {profile.core_skills[0]} & distributed systems, "
            f"I've built similar resilient pipelines and would love to connect!"
        )
        if len(connection_note) > 295:
            connection_note = connection_note[:292] + "..."

        # 4. Hiring Manager Cold Outreach Email
        cold_email = (
            f"Subject: Application & Inquiry: {job.title} – {profile.name}\n\n"
            f"Hi Hiring Team at {job.company},\n\n"
            f"I came across the {job.title} opening at {job.company} and was drawn to your focus on technical scale and product impact. "
            f"As a Senior Engineer with over {profile.min_years_experience} years of experience specializing in {', '.join(profile.core_skills[:3])}, "
            f"I have led the design and implementation of high-throughput distributed systems and automated decision pipelines.\n\n"
            f"Specifically, my background in building resilient, low-latency architectures directly mirrors the core competencies sought for this position. "
            f"I have attached my tailored resume for your review and would welcome a brief conversation to explore how I can contribute to your engineering goals.\n\n"
            f"Thank you for your time and consideration.\n\n"
            f"Best regards,\n"
            f"{profile.name}\n"
            f"{profile.email} | {profile.phone}\n"
            f"{profile.linkedin_url}"
        )

        return {
            "job_id": job.id,
            "job_title": job.title,
            "company": job.company,
            "primary_theme": primary_theme,
            "technical_questions": technical_questions,
            "behavioral_questions": behavioral_questions,
            "connection_note": connection_note,
            "connection_note_len": len(connection_note),
            "cold_email": cold_email,
        }
