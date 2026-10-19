"""
Comprehensive test suite for Job Hunter Multi-Agent System.
"""

import os
import tempfile
import pytest
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting, MatchReport, ScoredJob, ValidationResult
from job_hunter.orchestrator import JobHunterOrchestrator
from job_hunter.reviewer import MatchReviewer
from job_hunter.storage import LocalBrainStorage
from job_hunter.validator import JobValidator


def test_models_serialization():
    profile = CandidateProfile(name="Test User", title="Senior Engineer")
    p_dict = profile.to_dict()
    assert p_dict["name"] == "Test User"
    restored = CandidateProfile.from_dict(p_dict)
    assert restored.title == "Senior Engineer"

    job = JobPosting(
        title="AI Engineer",
        company="Test Labs",
        location="Remote",
        url="https://example.com/job/1",
        description="Build LLM agents and Python APIs.",
    )
    assert job.id != ""
    j_dict = job.to_dict()
    assert j_dict["title"] == "AI Engineer"
    restored_job = JobPosting.from_dict(j_dict)
    assert restored_job.id == job.id


def test_storage_operations():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        storage = LocalBrainStorage(db_path=db_path)
        job = JobPosting(
            title="Backend Dev",
            company="Acme Corp",
            location="Remote",
            url="https://example.com/job/backend",
            description="Python development.",
        )
        match = MatchReport(
            fit_score=0.85,
            fit_level="perfect",
            seniority_fit="level_matched",
            tech_stack_fit="strong_alignment",
            should_apply=True,
            should_apply_prob=0.88,
            confidence=0.75,
        )
        val = ValidationResult(is_valid=True, reasons=["All checks passed"])
        scored = ScoredJob(job=job, match=match, validation=val, status="shortlisted")

        storage.save(scored)
        assert storage.exists(job.id) is True

        jobs = storage.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].job.title == "Backend Dev"
        assert jobs[0].status == "shortlisted"

        # Update status
        storage.update_status(job.id, "applied")
        updated_jobs = storage.list_jobs(status="applied")
        assert len(updated_jobs) == 1

        stats = storage.get_stats()
        assert stats.get("applied") == 1
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_validator_dealbreakers():
    validator = JobValidator(min_fit_threshold=0.50)
    profile = CandidateProfile(
        dealbreakers=["US citizenship required", "Unpaid internship"]
    )
    match = MatchReport(
        fit_score=0.80,
        fit_level="perfect",
        seniority_fit="level_matched",
        tech_stack_fit="strong_alignment",
        should_apply=True,
        should_apply_prob=0.85,
        confidence=0.8,
    )

    # 1. Job with citizenship dealbreaker
    us_job = JobPosting(
        title="Defense Engineer",
        company="US Defense",
        location="Remote",
        url="https://example.com/1",
        description="Must be active US Citizen to apply.",
    )
    res_us = validator.validate(profile, us_job, match)
    assert res_us.is_valid is False
    assert any("Citizenship" in db for db in res_us.dealbreakers_triggered)

    # 2. Job with unpaid internship dealbreaker
    unpaid_job = JobPosting(
        title="Junior Intern",
        company="StartUp",
        location="Remote",
        url="https://example.com/2",
        description="Unpaid position for college credit only.",
    )
    res_unpaid = validator.validate(profile, unpaid_job, match)
    assert res_unpaid.is_valid is False
    assert any("Unpaid" in db for db in res_unpaid.dealbreakers_triggered)

    # 3. Clean job
    clean_job = JobPosting(
        title="Senior Python Engineer",
        company="Global Tech",
        location="Remote Worldwide",
        url="https://example.com/3",
        description="We are offering a competitive salary for a remote worldwide Senior Python Engineer. You will build high-scale distributed APIs, work with Docker and PostgreSQL, and design resilient microservices.",
    )
    res_clean = validator.validate(profile, clean_job, match)
    assert res_clean.is_valid is True
    assert len(res_clean.dealbreakers_triggered) == 0


def test_laya_client_and_reviewer_live():
    client = LayaClient()
    if not client.is_available():
        pytest.skip("Local Ollaya daemon not running")

    profile = CandidateProfile()
    job = JobPosting(
        title="Senior Python & Distributed Systems Engineer",
        company="CloudScale",
        location="Remote",
        url="https://example.com/job/senior-py",
        description="Looking for Senior Engineer with 6+ years in Python, distributed backend architectures, and Docker.",
    )

    reviewer = MatchReviewer(client)
    report = reviewer.review(profile, job)

    assert 0.0 <= report.fit_score <= 1.0
    assert report.fit_level in ("poor", "partial", "strong", "perfect")
    assert report.seniority_fit in ("level_matched", "level_mismatch")
    assert isinstance(report.should_apply, bool)


def test_orchestrator_batch():
    client = LayaClient()
    if not client.is_available():
        pytest.skip("Local Ollaya daemon not running")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        storage = LocalBrainStorage(db_path=db_path)
        orchestrator = JobHunterOrchestrator(laya_client=client, storage=storage)
        profile = CandidateProfile()

        jobs = [
            JobPosting(
                title="Senior AI Engineer",
                company="Agentic Systems",
                location="Remote",
                url="https://example.com/ai-eng",
                description="Build autonomous multi-agent pipelines with Python, Playwright and decision models. Requires 5+ years experience.",
            ),
            JobPosting(
                title="Unpaid Student Assistant",
                company="Volunteer NonProfit",
                location="Remote",
                url="https://example.com/unpaid-intern",
                description="Unpaid internship for college students. High school diploma required.",
            )
        ]

        summary = orchestrator.process_job_batch(jobs, profile)
        assert summary.discovered == 2
        assert len(summary.jobs) == 2

        # 1st job should be in inbox or shortlisted
        assert summary.jobs[0].status in ("shortlisted", "inbox")
        # 2nd job should be archived due to unpaid dealbreaker
        assert summary.jobs[1].status == "archived"
        assert any("Unpaid" in db for db in summary.jobs[1].validation.dealbreakers_triggered)

        # Database verification
        assert storage.exists(jobs[0].id) is True
        assert storage.exists(jobs[1].id) is True
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_pdf_resume_generator():
    from job_hunter.pdf_generator import PDFResumeGenerator, build_resume_html

    with tempfile.TemporaryDirectory() as tmpdir:
        profile = CandidateProfile(
            name="Example Candidate",
            title="Senior Software Engineer",
            email="candidate@example.invalid",
            phone="+90 555 123 4567",
            core_skills=["Python", "Distributed Systems", "Playwright"],
        )
        job = JobPosting(
            title="Lead AI Engineer",
            company="NeuralLabs",
            location="Remote",
            url="https://example.com/job/lead-ai",
            description="We are seeking a Lead AI Engineer with strong Python and distributed backend skills.",
        )
        tailored_data = {
            "tailored_headline": "Senior Software Engineer — Lead AI Engineer Specialist",
            "tailored_summary": "Seasoned engineer with deep expertise in Python architectures.",
            "tailored_bullets": [
                "Architected distributed microservices in Python.",
                "Integrated automated browser perception with sub-second decision pipelines."
            ],
            "matching_skills": ["Python", "Distributed Systems"]
        }

        # 1. HTML generation test
        html = build_resume_html(profile, job, tailored_data)
        assert profile.name in html
        assert "Example Company" in html or "Example University" in html
        assert "microservices" in html or "Python" in html

        # 2. Canonical LaTeX (.tex) generation and Tectonic compilation
        generator = PDFResumeGenerator(output_dir=tmpdir)
        pdf_path = generator.generate(profile, job, tailored_data, filename="test_resume.pdf")

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 1000  # Non-empty PDF document

        # 3. Verify .tex source is created and preserves exact Master CV macros
        tex_path = generator.last_generated_tex
        assert tex_path is not None and tex_path.exists()
        tex_content = tex_path.read_text(encoding="utf-8")
        assert r"\documentclass[10pt,a4paper]{article}" in tex_content
        assert r"\newcommand{\role}" in tex_content
        assert r"\newcommand{\project}" in tex_content
        assert r"\definecolor{heading}{HTML}{172033}" in tex_content
        assert "Example Company" in tex_content
        assert "Example University" in tex_content


def test_interview_prep_assistant():
    from job_hunter.interview_prep import InterviewPrepAssistant

    client = LayaClient()
    prep_assistant = InterviewPrepAssistant(laya_client=client)

    profile = CandidateProfile(
        name="Example Candidate",
        title="Senior Software Engineer",
        min_years_experience=6,
        core_skills=["Python", "Distributed Systems", "PostgreSQL"],
    )
    job = JobPosting(
        title="Senior Distributed Systems Architect",
        company="ScaleData Corp",
        location="Remote Worldwide",
        url="https://example.com/scaledata",
        description="Seeking an architect for high-throughput Python and distributed Kafka architectures.",
    )

    prep_kit = prep_assistant.generate_prep_kit(profile, job)

    assert prep_kit["job_title"] == "Senior Distributed Systems Architect"
    assert prep_kit["company"] == "ScaleData Corp"

    # Verify 5 Technical Questions
    assert len(prep_kit["technical_questions"]) == 5
    for q in prep_kit["technical_questions"]:
        assert "question" in q and len(q["question"]) > 10
        assert "talking_points" in q and len(q["talking_points"]) > 20

    # Verify 3 Behavioral STAR Questions
    assert len(prep_kit["behavioral_questions"]) == 3
    for b in prep_kit["behavioral_questions"]:
        assert "question" in b
        assert "guide" in b

    # Verify LinkedIn Note length constraint (< 300 chars)
    note = prep_kit["connection_note"]
    assert len(note) <= 300
    assert "ScaleData Corp" in note or "your team" in note

    # Verify Cold Email format
    assert "ScaleData Corp" in prep_kit["cold_email"]
    assert profile.email in prep_kit["cold_email"]


def test_desktop_notifier():
    from job_hunter.notifier import DesktopNotifier

    # Direct notification (should gracefully handle execution)
    res = DesktopNotifier.notify(
        title="Job Hunter Test",
        subtitle="Test Subtitle",
        message="Test message from unit test suite",
        sound=False,
    )
    assert isinstance(res, bool)

    # Job match alert with low score (should return False)
    low_job = ScoredJob(
        job=JobPosting(title="Intern", company="Co", location="Remote", url="https://ex.com", description="Short internship description"),
        match=MatchReport(
            fit_score=0.30,
            fit_level="poor",
            seniority_fit="level_mismatch",
            tech_stack_fit="weak_alignment",
            should_apply=False,
            should_apply_prob=0.10,
            confidence=0.5,
        ),
        validation=ValidationResult(is_valid=True),
        status="inbox",
    )
    assert DesktopNotifier.notify_job_match(low_job, min_score_threshold=0.70) is False

    # Job match alert with high score
    high_job = ScoredJob(
        job=JobPosting(title="Senior AI Engineer", company="Ollaya Labs", location="Remote", url="https://ex.com", description="High-scale AI agent engineer role with Python."),
        match=MatchReport(
            fit_score=0.92,
            fit_level="perfect",
            seniority_fit="level_matched",
            tech_stack_fit="strong_alignment",
            should_apply=True,
            should_apply_prob=0.95,
            confidence=0.9,
        ),
        validation=ValidationResult(is_valid=True),
        status="shortlisted",
    )
    # On macOS this returns True, on other OS False
    notified = DesktopNotifier.notify_job_match(high_job, min_score_threshold=0.70)
    assert isinstance(notified, bool)


def test_easy_apply_screening_decision():
    from job_hunter.easy_apply import EasyApplyAgent

    client = LayaClient()
    agent = EasyApplyAgent(laya_client=client)

    profile = CandidateProfile(
        name="Example Candidate",
        title="Senior Software Engineer",
        min_years_experience=6,
        core_skills=["Python", "FastAPI", "PostgreSQL"],
    )

    options = {
        "opt_yes": "Yes, I have 5+ years of experience with Python",
        "opt_no": "No, I am completely new to Python",
    }
    question = "Do you have professional hands-on experience developing backend systems with Python?"

    choice = agent._decide_screening_answer(profile, question, options)
    assert choice in options
    if client.is_available():
        # Laya should select the positive experience option
        assert choice == "opt_yes"


def test_multi_board_url_builders():
    from job_hunter.multi_board import MultiBoardScraper
    from job_hunter.orchestrator import JobHunterOrchestrator

    orchestrator = JobHunterOrchestrator(laya_client=LayaClient(), storage=LocalBrainStorage(db_path=":memory:"))
    scraper = MultiBoardScraper(orchestrator=orchestrator)

    li_url = scraper.build_search_url("linkedin", "AI Engineer", "Remote")
    assert "linkedin.com/jobs/search" in li_url
    assert "AI+Engineer" in li_url or "AI%20Engineer" in li_url

    wwr_url = scraper.build_search_url("wwr", "Python", "Remote")
    assert "weworkremotely.com" in wwr_url
    assert "Python" in wwr_url

    indeed_url = scraper.build_search_url("indeed", "Senior Developer", "Remote")
    assert "indeed.com/jobs" in indeed_url


def test_email_inbox_watcher_triage():
    from job_hunter.email_watcher import EmailInboxWatcher

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        storage = LocalBrainStorage(db_path=db_path)
        client = LayaClient()
        watcher = EmailInboxWatcher(laya_client=client, storage=storage, enable_notifications=False)

        # 1. Add an active job to storage
        target_job = ScoredJob(
            job=JobPosting(
                title="Staff AI Engineer",
                company="Example Co",
                location="Remote",
                url="https://example.invalid/jobs/1",
                description="Lead distributed decision pipelines and AI model inference in Python.",
            ),
            match=MatchReport(
                fit_score=0.90,
                fit_level="perfect",
                seniority_fit="level_matched",
                tech_stack_fit="strong_alignment",
                should_apply=True,
                should_apply_prob=0.92,
                confidence=0.88,
            ),
            validation=ValidationResult(is_valid=True),
            status="applied",
        )
        storage.save(target_job)

        # 2. Process an incoming interview email
        interview_email = {
            "id": "email_interview_test_1",
            "sender": "recruiter@example.invalid",
            "subject": "Interview Invitation: Staff AI Engineer at Example Co",
            "body": (
                "Hi there,\n\n"
                "We reviewed your application for the Staff AI Engineer role and would like to schedule a 45-minute technical conversation. "
                "Please choose a time on our calendar: https://example.invalid/calendar\n\n"
                "Best regards,\nExample Co Hiring Team"
            ),
        }

        event = watcher.triage_email(
            subject=interview_email["subject"],
            sender=interview_email["sender"],
            body=interview_email["body"],
            message_id=interview_email["id"],
        )

        assert event.category == "interview_invitation"
        assert event.matched_job_id == target_job.job.id

        # Verify job status in storage was automatically updated to interview_scheduled
        updated_job = storage.get_job_by_id(target_job.job.id)
        assert updated_job is not None
        assert updated_job.status == "interview_scheduled"

        # Verify event persisted in email_events table
        events = storage.list_email_events()
        assert len(events) >= 1
        assert events[0].category == "interview_invitation"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_outreach_sequencer_workflow():
    from job_hunter.outreach_sequencer import OutreachSequencer

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        storage = LocalBrainStorage(db_path=db_path)
        sequencer = OutreachSequencer(storage=storage)

        profile = CandidateProfile(
            name="Example Candidate",
            title="Senior Software Engineer",
            min_years_experience=6,
            core_skills=["Python", "FastAPI", "Distributed Systems"],
        )
        job = JobPosting(
            title="Senior Distributed Systems Architect",
            company="DataMesh Labs",
            location="Remote",
            url="https://datamesh.io/careers/senior-architect",
            description="Seeking architect with strong Python and event-driven microservices background.",
        )

        steps = sequencer.generate_sequence(profile, job)
        assert len(steps) == 4  # Day 0 LI, Day 0 Email, Day 5 Email, Day 12 Email

        # Check Day 0 LinkedIn length constraint
        li_step = next(s for s in steps if s.channel == "linkedin")
        assert len(li_step.body) <= 300
        assert "DataMesh Labs" in li_step.body or "your team" in li_step.body

        # Check Day 5 and Day 12 exist and are in draft
        day_5_step = next(s for s in steps if s.step_day == 5)
        assert day_5_step.status == "draft"
        assert "Following up" in day_5_step.subject

        day_12_step = next(s for s in steps if s.step_day == 12)
        assert day_12_step.status == "draft"

        # Test Approval flow
        success = sequencer.approve_step(day_5_step.id)
        assert success is True
        reviewed_steps = sequencer.get_job_sequence(job.id)
        updated_d5 = next(s for s in reviewed_steps if s.id == day_5_step.id)
        assert updated_d5.status == "approved"

        # Test Mark as Sent
        sequencer.mark_sent(day_5_step.id)
        sent_steps = sequencer.get_job_sequence(job.id)
        assert next(s for s in sent_steps if s.id == day_5_step.id).status == "sent"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_company_culture_agent_analysis():
    from job_hunter.culture_intelligence import CompanyCultureAgent

    client = LayaClient()
    agent = CompanyCultureAgent(laya_client=client)

    job = JobPosting(
        title="Senior AI Platform Engineer",
        company="HuggingFace",
        location="Remote Worldwide",
        url="https://huggingface.co/jobs/1",
        description="We are building open-source AI platform pipelines. Strong async culture, CI/CD, remote-friendly team.",
    )

    report = agent.analyze_company(company="HuggingFace", job=job)

    assert report.company == "HuggingFace"
    assert 0.0 <= report.culture_score <= 1.0
    assert report.work_life_balance_signal in ("high", "moderate", "challenging")
    assert report.tech_debt_risk in ("low", "medium", "high")
    assert report.engineering_autonomy in ("high_autonomy", "moderate", "hierarchical")
    assert len(report.highlights) > 0
    assert "Remote" in report.estimated_salary_range or "$" in report.estimated_salary_range


def test_batch_apply_orchestrator_initialization():
    from job_hunter.batch_apply import BatchApplyOrchestrator

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        storage = LocalBrainStorage(db_path=db_path)
        client = LayaClient()
        batch_orchestrator = BatchApplyOrchestrator(laya_client=client, storage=storage)

        profile = CandidateProfile()
        # Empty shortlisted test
        result = batch_orchestrator.execute_batch_apply(profile=profile, job_ids=[])
        assert result.total_requested == 0
        assert result.applied_count == 0
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

