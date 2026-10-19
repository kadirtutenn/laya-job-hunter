"""
Command line interface for local job search and tracking.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional
from job_hunter.dashboard import DashboardServer
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting
from job_hunter.orchestrator import JobHunterOrchestrator
from job_hunter.storage import LocalBrainStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("job_hunter")


def load_profile(profile_path: Optional[str] = None) -> CandidateProfile:
    default_path = Path(__file__).parent / "sample_profile.json"
    target = Path(profile_path) if profile_path else default_path
    if target.exists():
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
                return CandidateProfile.from_dict(data)
        except Exception as e:
            logger.warning(f"Could not parse profile at {target} ({e}), using defaults.")
    return CandidateProfile()


def format_bar(score: float, width: int = 16) -> str:
    filled = int(round(score * width))
    empty = width - filled
    return "█" * filled + "░" * empty


def print_job_card(scored_job):
    job = scored_job.job
    match = scored_job.match
    val = scored_job.validation
    score_pct = int(round(match.fit_score * 100))

    status_tag = f"[{scored_job.status.upper()}]"
    print(f"\n{'='*70}")
    print(f" {status_tag} {job.title} @ {job.company}")
    print(f" Konum: {job.location} | Kaynak: {job.source}")
    print(f" URL:   {job.url}")
    print(f"{'-'*70}")
    print(f" Laya Eşleşme Skoru:   {format_bar(match.fit_score)} %{score_pct} ({match.fit_level})")
    print(f" Başvuru Tavsiyesi:    {'EVET' if match.should_apply else 'HAYIR'} (Olasılık: %{match.should_apply_prob*100:.1f})")
    print(f" Kıdem Uyumu:          {match.seniority_fit}")
    print(f" Teknoloji Yığını:     {match.tech_stack_fit}")
    if val.dealbreakers_triggered:
        print(f" [!] Engeller:         {', '.join(val.dealbreakers_triggered)}")
    print(f"{'='*70}")


def cmd_login(args):
    """Opens a headful interactive Chrome window for logging into LinkedIn or other job portals."""
    from job_hunter.navigator import BrowserNavigator
    client = LayaClient()
    user_data_dir = getattr(args, "user_data_dir", None)
    navigator = BrowserNavigator(laya_client=client, headless=False, user_data_dir=user_data_dir)
    print(f"\n[+] LinkedIn Giriş Oturumu Başlatılıyor...")
    print(f"    Giriş URL:      {args.url}")
    print(f"    Profil Dizini:  {navigator.user_data_dir}")
    navigator.open_interactive_login(target_url=args.url)


def cmd_hunt(args):
    """Executes live autonomous browser navigation."""
    profile = load_profile(args.profile)
    client = LayaClient()
    storage = LocalBrainStorage(args.db)
    orchestrator = JobHunterOrchestrator(laya_client=client, storage=storage, model=args.model)

    if not client.is_available():
        print("[!] Ollaya daemon unreachable at http://127.0.0.1:11435")
        print("    Please run: 'ollaya serve' and ensure laya model is downloaded.")
        sys.exit(1)

    user_data_dir = getattr(args, "user_data_dir", None)
    print(f"\n[+] Otonom Ajan Başlatılıyor...")
    print(f"    Hedef Profil: {profile.name} ({profile.title})")
    print(f"    Başlangıç URL: {args.url}")
    print(f"    Maksimum İlan: {args.max_jobs}")
    print(f"    Tarayıcı Modu: {'Headless' if not args.headful else 'Görünür (Headful)'}")
    print(f"    Karar Modeli:  {args.model} (:11435)")

    summary = orchestrator.hunt_from_browser(
        start_url=args.url,
        profile=profile,
        max_jobs=args.max_jobs,
        headless=not args.headful,
        user_data_dir=user_data_dir,
        on_progress=print_job_card,
    )

    print(f"\n--- [Avlama Özeti] ---")
    print(f"Toplam Taranan:       {summary.discovered}")
    print(f"Shortlist (≥ 70%):    {summary.shortlisted}")
    print(f"Inbox (İnceleme):     {summary.inbox}")
    print(f"Elenenler:            {summary.archived}")
    print(f"Mükerrer Geçilen:     {summary.skipped_duplicates}")
    print(f"\nSonuçlar yerel SQLite veritabanına kaydedildi: {storage.db_path}")


def cmd_demo(args):
    """Runs a fast demo triage over curated real-world job postings to test Laya matching."""
    profile = load_profile(args.profile)
    client = LayaClient()
    storage = LocalBrainStorage(args.db)
    orchestrator = JobHunterOrchestrator(laya_client=client, storage=storage, model=args.model)

    if not client.is_available():
        print("[!] Ollaya daemon unreachable at http://127.0.0.1:11435")
        print("    Please run: 'ollaya serve' and ensure laya model is downloaded.")
        sys.exit(1)

    print(f"\n[+] Demo Triage Başlatılıyor (Örnek İlan Havuzu)...")
    print(f"    Hedef Profil: {profile.name} ({profile.title})")

    # Sample curated real-world postings for demonstration
    sample_jobs = [
        JobPosting(
            title="Senior Autonomous Agent & Python Backend Engineer",
            company="NeuralFlow Labs",
            location="Remote (Europe / Worldwide)",
            url="https://example.com/jobs/senior-agent-engineer",
            description=(
                "We are seeking a Senior AI/Backend Engineer with strong expertise in Python, Rust, "
                "and autonomous agent design. You will build high-throughput decision systems, "
                "integrate LLMs and local ONNX decision models, and design browser automation with Playwright. "
                "Requires 5+ years backend experience, strong async Python, and Docker."
            ),
            tags=["Python", "Rust", "Autonomous Agents", "Playwright", "FastAPI"],
            source="demo-feed",
        ),
        JobPosting(
            title="Staff Distributed Systems Architect",
            company="Apex Data Grid",
            location="Remote (Worldwide)",
            url="https://example.com/jobs/staff-architect",
            description=(
                "Seeking Staff Systems Engineer with 8+ years experience in distributed databases, "
                "Rust, memory-efficient networking, and concurrency. Deep knowledge of Raft/Paxos and low-latency APIs."
            ),
            tags=["Rust", "Distributed Systems", "Architecture"],
            source="demo-feed",
        ),
        JobPosting(
            title="Junior Frontend React Intern",
            company="SaaS Startup Co",
            location="Remote",
            url="https://example.com/jobs/junior-react-intern",
            description=(
                "Entry level junior internship for undergraduate students learning HTML, CSS and basic React. "
                "Unpaid internship for college credit only. No prior experience required."
            ),
            tags=["React", "Junior", "Internship"],
            source="demo-feed",
        ),
        JobPosting(
            title="Principal Defense Systems Engineer",
            company="Defense Dynamics LLC",
            location="Onsite - Washington DC",
            url="https://example.com/jobs/defense-systems",
            description=(
                "Strict Requirement: Must be active US Citizen with Top Secret Security Clearance. "
                "Work strictly onsite 5 days a week at secure facility in DC. C++ legacy radar systems."
            ),
            tags=["C++", "Defense", "Security Clearance"],
            source="demo-feed",
        ),
    ]

    summary = orchestrator.process_job_batch(
        jobs=sample_jobs,
        profile=profile,
        on_progress=print_job_card,
    )

    print(f"\n--- [Triage Tamamlandı] ---")
    print(f"Toplam İncelenen:     {summary.discovered}")
    print(f"Shortlist (≥ 70%):    {summary.shortlisted}")
    print(f"Inbox (İnceleme):     {summary.inbox}")
    print(f"Elenenler:            {summary.archived}")
    print(f"Mükerrer Geçilen:     {summary.skipped_duplicates}")


def cmd_inbox(args):
    """Lists jobs saved in local brain."""
    storage = LocalBrainStorage(args.db)
    jobs = storage.list_jobs(status=args.status if args.status != "all" else None)

    if not jobs:
        print("[!] Yerel hafızada kayıtlı ilan bulunamadı.")
        return

    print(f"\n--- [Yerel Hafıza: {len(jobs)} İlan] ---")
    for scored in jobs:
        print_job_card(scored)


def cmd_serve(args):
    """Starts the local dashboard server."""
    profile = load_profile(args.profile)
    storage = LocalBrainStorage(args.db)
    server = DashboardServer(storage=storage, profile=profile, port=args.port)

    # Export a static copy as well
    html_path = server.export_html(args.export)
    print(f"[+] Statik HTML raporu oluşturuldu: {html_path}")
    print(f"[+] Web Dashboard başlatılıyor: http://localhost:{args.port}")
    print("    (Durdurmak için Ctrl+C tuşlayın)\n")
    server.run()


def cmd_export(args):
    """Exports static HTML report."""
    profile = load_profile(args.profile)
    storage = LocalBrainStorage(args.db)
    server = DashboardServer(storage=storage, profile=profile)
    html_path = server.export_html(args.output)
    print(f"[+] HTML Raporu başarıyla oluşturuldu: {html_path}")


def cmd_resume(args):
    """Generates an ATS-optimized PDF resume tailored to a specific job."""
    from job_hunter.pdf_generator import PDFResumeGenerator
    from job_hunter.tailor import CVTailor

    profile = load_profile(args.profile)
    storage = LocalBrainStorage(args.db)
    client = LayaClient()
    jobs = storage.list_jobs()

    if not jobs:
        print("[!] Yerel hafızada kayıtlı ilan bulunamadı.")
        return

    target_job = None
    if args.job_id:
        target_job = next((j.job for j in jobs if j.job.id == args.job_id), None)
    if not target_job:
        target_job = jobs[0].job

    tailor = CVTailor(client)
    data = tailor.tailor(profile, target_job)
    pdf_gen = PDFResumeGenerator(output_dir=args.out_dir)
    out_path = pdf_gen.generate(profile, target_job, data, filename=args.filename)

    print(f"\n[+] ATS Uyumlu Canonical LaTeX ve PDF Özgeçmiş Başarıyla Oluşturuldu:")
    print(f"    Hedef İlan:         {target_job.title} @ {target_job.company}")
    print(f"    LaTeX Kaynak (.tex): {pdf_gen.last_generated_tex}")
    print(f"    Derlenmiş PDF (.pdf): {out_path} ({out_path.stat().st_size} bytes)")
    print(f"    Derleme Motoru:     Tectonic (Doğrudan Vektör PDF)\n")


def cmd_prep(args):
    """Generates an interview prep kit and recruiter outreach pack."""
    from job_hunter.interview_prep import InterviewPrepAssistant

    profile = load_profile(args.profile)
    storage = LocalBrainStorage(args.db)
    client = LayaClient()
    jobs = storage.list_jobs()

    if not jobs:
        print("[!] Yerel hafızada kayıtlı ilan bulunamadı.")
        return

    target_job = None
    if args.job_id:
        target_job = next((j.job for j in jobs if j.job.id == args.job_id), None)
    if not target_job:
        target_job = jobs[0].job

    assistant = InterviewPrepAssistant(client)
    kit = assistant.generate_prep_kit(profile, target_job)

    print(f"\n{'='*70}")
    print(f" 🎯 MÜLAKAT HAZIRLIK KİTİ: {target_job.title} @ {target_job.company}")
    print(f" Ana Teknik Odak: {kit['primary_theme']}")
    print(f"{'='*70}")

    print(f"\n[1] 5 HEDEFE ÖZEL TEKNİK MÜLAKAT SORUSU & İPUÇLARI:")
    for idx, q in enumerate(kit["technical_questions"], 1):
        print(f"  {idx}. {q['question']}")
        print(f"     -> İpucu: {q['talking_points']}\n")

    print(f"[2] 3 DAVRANIŞSAL (STAR) MÜLAKAT SORUSU:")
    for idx, q in enumerate(kit["behavioral_questions"], 1):
        print(f"  {idx}. {q['question']}")
        print(f"     -> Rehber: {q['guide']}\n")

    print(f"[3] LINKEDIN BAĞLANTI NOTU (< 300 KARAKTER):")
    print(f"  \"{kit['connection_note']}\" (Karakter: {kit['connection_note_len']})\n")

    print(f"[4] İŞE ALIM YÖNETİCİSİNE DOĞRUDAN E-POSTA:")
    print(kit['cold_email'])
    print(f"{'='*70}\n")


def cmd_multi_hunt(args):
    """Runs concurrent multi-board search across LinkedIn, WWR, Indeed, Wellfound."""
    from job_hunter.multi_board import MultiBoardScraper

    profile = load_profile(args.profile)
    client = LayaClient()
    storage = LocalBrainStorage(args.db)
    orchestrator = JobHunterOrchestrator(laya_client=client, storage=storage, model=args.model)

    scraper = MultiBoardScraper(orchestrator=orchestrator, enable_notifications=not args.no_notify)
    portals = [p.strip() for p in args.portals.split(",") if p.strip()]

    print(f"\n[+] Çoklu Platform Otonom Avı Başlatılıyor...")
    print(f"    Portallar:     {', '.join(portals)}")
    print(f"    Arama İfadesi: {args.query}")
    print(f"    Tarayıcı:      {'Görünür (Headful)' if args.headful else 'Headless'}")

    res = scraper.run_multi_board_hunt(
        portals=portals,
        keywords=args.query,
        profile=profile,
        max_jobs_per_portal=args.max_per_portal,
        headful=args.headful,
        on_progress=print_job_card,
    )

    print(f"\n--- [Çoklu Av Özeti] ---")
    print(f"Toplam Taranan:    {res['total_discovered']}")
    print(f"Shortlist (≥ 70%): {res['shortlisted']}")


def cmd_email_triage(args):
    """Processes job-hunting emails locally and updates pipeline status."""
    from job_hunter.email_watcher import EmailInboxWatcher

    client = LayaClient()
    storage = LocalBrainStorage(args.db)
    watcher = EmailInboxWatcher(laya_client=client, storage=storage)

    print("\n[+] E-Posta Gelen Kutusu Triajı Başlatılıyor (Local Brain)...")

    if args.mock:
        mock_emails = [
            {
                "id": "mock_interview_1",
                "sender": "recruiter@example.invalid",
                "subject": "Interview Invitation: Senior Software Engineer at Example Co",
                "body": (
                    "Hi there,\n\n"
                    "Thank you for your application to Example Co! We reviewed your background with distributed systems "
                    "and would love to invite you to a 45-minute technical interview with our Lead Architect.\n\n"
                    "Please select a slot: https://example.invalid/calendar\n\n"
                    "Best regards,\nTalent Team"
                ),
            },
            {
                "id": "mock_test_1",
                "sender": "hiring@datacorp.io",
                "subject": "Technical Assessment: Senior Distributed Systems Architect",
                "body": (
                    "Hello there,\n\n"
                    "We are pleased to invite you to the next step of our hiring process: a 90-minute online coding challenge on HackerRank.\n"
                    "Link: https://hackerrank.com/test/datacorp-123\n\n"
                    "Good luck!"
                ),
            },
            {
                "id": "mock_rejection_1",
                "sender": "no-reply@legacytech.com",
                "subject": "Update on your application for Backend Engineer",
                "body": (
                    "Dear Candidate,\n\n"
                    "Thank you for your interest. Unfortunately, after careful consideration, we have decided to pursue other candidates.\n"
                    "We wish you all the best in your job search."
                ),
            },
        ]
        events = watcher.process_mock_inbox(mock_emails)
    else:
        if not args.host or not args.user or not args.password:
            print("[!] IMAP bağlantısı için --host, --user ve --password gereklidir.")
            print("    Test amaçlı çalıştırmak için: python3 -m job_hunter email-triage --mock")
            return
        events = watcher.sync_imap_inbox(
            host=args.host,
            username=args.user,
            password=args.password,
            limit=args.limit,
        )

    print(f"\n[+] {len(events)} E-Posta Başarıyla İşlendi:")
    for ev in events:
        cat_symbol = "🎉" if ev.category == "interview_invitation" else ("📝" if ev.category == "assessment_test" else "📬")
        print(f"  {cat_symbol} [{ev.category.upper()}] {ev.subject[:55]}...")
        print(f"     Gönderen: {ev.sender} | Eşleşen Şirket: {ev.matched_company or 'Bilinmiyor'}")
        if ev.action_taken:
            print(f"     Aksiyon: {ev.action_taken}")
        print()


def cmd_sequence(args):
    """Generates or reviews multi-touch outreach sequences."""
    from job_hunter.outreach_sequencer import OutreachSequencer

    storage = LocalBrainStorage(args.db)
    sequencer = OutreachSequencer(storage)
    profile = load_profile(args.profile)

    if args.approve:
        success = sequencer.approve_step(args.approve)
        print(f"Adım [{args.approve}] Onaylandı: {'Başarılı' if success else 'Bulunamadı'}")
        return

    if args.job_id:
        target = storage.get_job_by_id(args.job_id)
        if not target:
            print(f"[!] İlan bulunamadı: {args.job_id}")
            return
        steps = sequencer.generate_sequence(profile, target.job)
        print(f"\n[+] '{target.job.title}' İçin 3 Aşamalı Takip Dizisi Oluşturuldu:")
        for s in steps:
            print(f"\n--- [DAY {s.step_day} - {s.channel.upper()}] {s.subject} (ID: {s.id}) ---")
            print(f"Durum: {s.status.upper()} | Planlanan Tarih: {s.scheduled_for}")
            print(f"{s.body}\n")
    else:
        # List review queue
        steps = sequencer.get_review_queue(status=None if args.all else "draft")
        print(f"\n[+] İletişim Onay Kuyruğu ({len(steps)} Adım):")
        for s in steps:
            print(f" • [DAY {s.step_day}] [{s.status.upper()}] {s.subject} (ID: {s.id})")


def cmd_culture(args):
    """Generates company & engineering culture intelligence."""
    from job_hunter.culture_intelligence import CompanyCultureAgent

    client = LayaClient()
    storage = LocalBrainStorage(args.db)
    agent = CompanyCultureAgent(laya_client=client, storage=storage)

    job = None
    company_name = args.company
    if args.job_id:
        j_obj = storage.get_job_by_id(args.job_id)
        if j_obj:
            job = j_obj.job
            company_name = job.company

    if not company_name:
        print("[!] Lütfen --company veya --job-id parametresi verin.")
        return

    print(f"\n[+] Şirket Kültür İstihbaratı Analiz Ediliyor: {company_name}...")
    report = agent.analyze_company(company_name, job)

    print(f"\n{'='*70}")
    print(f" ŞİRKET KÜLTÜR İSTİHBARATI: {report.company.upper()}")
    print(f"{'-'*70}")
    print(f" Genel Kültür Puanı:      %{int(report.culture_score*100)} ({format_bar(report.culture_score)})")
    print(f" Work-Life Balance:       {report.work_life_balance_signal.upper()}")
    print(f" Teknik Borç (Tech Debt): {report.tech_debt_risk.upper()}")
    print(f" Mühendislik Otonomisi:   {report.engineering_autonomy.upper()}")
    print(f" Tahmini Maaş Seviyesi:   {report.estimated_salary_range}")
    if report.github_signals.get("org_found"):
        print(f" GitHub Ayak İzi:         {report.github_signals.get('repo_count')} Kamu Repo | {', '.join(report.github_signals.get('top_languages', []))}")
    print(f"\n [✓] Pozitif Kültür Özellikleri:")
    for h in report.highlights:
        print(f"   • {h}")
    if report.red_flags:
        print(f"\n [!] Dikkat Edilmesi Gereken Risk / Red Flag Sinyalleri:")
        for rf in report.red_flags:
            print(f"   • {rf}")
    print(f"{'='*70}\n")


def cmd_batch_apply(args):
    """Runs 1-click batch application for shortlisted jobs."""
    from job_hunter.batch_apply import BatchApplyOrchestrator

    profile = load_profile(args.profile)
    client = LayaClient()
    storage = LocalBrainStorage(args.db)
    orchestrator = BatchApplyOrchestrator(laya_client=client, storage=storage)

    print(f"\n[+] 1-Click Toplu Başvuru Kuyruğu Başlatılıyor...")
    print(f"    Maksimum Başvuru: {args.limit}")
    print(f"    Görünür Tarayıcı: {'Açık (Headful)' if args.headful else 'Headless'}")

    res = orchestrator.execute_batch_apply(
        profile=profile,
        limit=args.limit,
        headful=args.headful,
    )

    print(f"\n--- [Toplu Başvuru Sonucu] ---")
    print(f"İşlenen Toplam İlan: {res.total_requested}")
    print(f"Form Taslakları Hazır: {res.prepared_count}")
    print(f"İnceleme Gereken:    {res.failed_count}")
    for item in res.results:
        print(f" • {item.get('title')} @ {item.get('company')}: {item.get('status').upper()}")


def main():
    parser = argparse.ArgumentParser(
        description="Local job search and application tracking with Ollaya/Laya"
    )
    parser.add_argument("--db", default="job_hunter_brain.db", help="Path to SQLite database")
    parser.add_argument("--model", default="laya", help="Ollaya decision model (default: laya)")
    parser.add_argument("--profile", default=None, help="Path to candidate profile JSON")
    parser.add_argument("--profile-dir", default=None, dest="user_data_dir", help="Chrome persistent user data directory")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # 0. login
    login_parser = subparsers.add_parser("login", help="Open Chrome window to log in to LinkedIn")
    login_parser.add_argument(
        "--url",
        default="https://www.linkedin.com/login",
        help="Login URL (default: https://www.linkedin.com/login)",
    )

    # 1. hunt
    hunt_parser = subparsers.add_parser("hunt", help="Autonomously navigate browser and harvest jobs")
    hunt_parser.add_argument(
        "--url",
        default="https://weworkremotely.com/categories/remote-programming-jobs",
        help="Initial job listing URL",
    )
    hunt_parser.add_argument("--max-jobs", type=int, default=5, help="Maximum jobs to harvest")
    hunt_parser.add_argument("--headful", action="store_true", help="Launch visible browser")

    # 2. multi-hunt
    multi_parser = subparsers.add_parser("multi-hunt", help="Search across multiple job portals concurrently")
    multi_parser.add_argument("--portals", default="wwr,linkedin", help="Comma-separated portals: linkedin,wwr,indeed,wellfound")
    multi_parser.add_argument("--query", default="Senior Python Engineer", help="Job search query")
    multi_parser.add_argument("--max-per-portal", type=int, default=3, help="Max jobs per portal")
    multi_parser.add_argument("--headful", action="store_true", help="Launch visible browser")
    multi_parser.add_argument("--no-notify", action="store_true", help="Disable desktop notifications")

    # 3. demo
    demo_parser = subparsers.add_parser("demo", help="Run instant triage demo with real sample jobs")

    # 4. inbox
    inbox_parser = subparsers.add_parser("inbox", help="View jobs saved in local brain")
    inbox_parser.add_argument("--status", default="all", choices=["all", "inbox", "shortlisted", "applied", "archived"])

    # 5. resume
    resume_parser = subparsers.add_parser("resume", help="Generate ATS-optimized PDF resume tailored to a job")
    resume_parser.add_argument("--job-id", default=None, help="Specific Job ID from database")
    resume_parser.add_argument("--out-dir", default="tailored_resumes", help="Output directory")
    resume_parser.add_argument("--filename", default=None, help="Custom filename")

    # 6. prep
    prep_parser = subparsers.add_parser("prep", help="Generate interview prep kit and recruiter outreach pack")
    prep_parser.add_argument("--job-id", default=None, help="Specific Job ID from database")

    # 7. serve
    serve_parser = subparsers.add_parser("serve", help="Run local interactive web dashboard")
    serve_parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    serve_parser.add_argument("--export", default="job_hunter_dashboard.html", help="Path for HTML export")

    # 8. export
    export_parser = subparsers.add_parser("export", help="Export static HTML report")
    export_parser.add_argument("--output", default="job_hunter_dashboard.html", help="Output file path")

    # 9. email-triage (Level 3)
    email_parser = subparsers.add_parser("email-triage", help="Triage job hunt emails and auto-update application status")
    email_parser.add_argument("--mock", action="store_true", help="Run with realistic sample interview/rejection emails")
    email_parser.add_argument("--host", default=None, help="IMAP Host (e.g. imap.gmail.com)")
    email_parser.add_argument("--user", default=None, help="IMAP Username / Email")
    email_parser.add_argument("--password", default=None, help="IMAP Password / App Password")
    email_parser.add_argument("--limit", type=int, default=15, help="Number of emails to fetch")

    # 10. sequence (Level 3)
    seq_parser = subparsers.add_parser("sequence", help="Generate or review 3-touch outreach sequences")
    seq_parser.add_argument("--job-id", default=None, help="Generate Day 0/5/12 sequence for specific Job ID")
    seq_parser.add_argument("--all", action="store_true", help="List all sequence steps including approved/sent")
    seq_parser.add_argument("--approve", default=None, help="Approve specific step ID")

    # 11. culture (Level 3)
    cult_parser = subparsers.add_parser("culture", help="Analyze company engineering culture, tech debt, and salary range")
    cult_parser.add_argument("--company", default=None, help="Company name to analyze")
    cult_parser.add_argument("--job-id", default=None, help="Job ID to analyze from database")

    # 12. batch-apply (Level 3)
    batch_parser = subparsers.add_parser("batch-apply", help="1-click batch application for shortlisted jobs")
    batch_parser.add_argument("--limit", type=int, default=3, help="Max jobs to apply to in this batch")
    batch_parser.add_argument("--headful", action="store_true", help="Run browser visibly")

    args = parser.parse_args()

    if args.command == "login":
        cmd_login(args)
    elif args.command == "hunt":
        cmd_hunt(args)
    elif args.command == "multi-hunt":
        cmd_multi_hunt(args)
    elif args.command == "demo":
        cmd_demo(args)
    elif args.command == "inbox":
        cmd_inbox(args)
    elif args.command == "resume":
        cmd_resume(args)
    elif args.command == "prep":
        cmd_prep(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "email-triage":
        cmd_email_triage(args)
    elif args.command == "sequence":
        cmd_sequence(args)
    elif args.command == "culture":
        cmd_culture(args)
    elif args.command == "batch-apply":
        cmd_batch_apply(args)


if __name__ == "__main__":
    main()
