"""
Dynamic ATS-Optimized Resume Exporter (LaTeX & PDF):
Generates targeted, high-scoring ATS resumes tailored to specific job postings on-the-fly.
Primary Engine: Candidate supplied LaTeX (.tex) with local Tectonic compiler.
Fallback Engine: Headless Chromium via Playwright (if LaTeX compiler is unavailable).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from job_hunter.models import CandidateProfile, JobPosting
from job_hunter.latex_generator import (
    build_resume_latex,
    compile_latex_with_tectonic,
    get_tectonic_path,
)

logger = logging.getLogger(__name__)


def build_resume_html(profile: CandidateProfile, job: JobPosting, tailored_data: Dict[str, Any]) -> str:
    """Render only candidate-provided profile facts; never inject sample experience."""
    import html
    if not profile.name or not profile.summary:
        raise ValueError("Add your own verified candidate profile and CV evidence before generating a resume.")
    esc = lambda value: html.escape(str(value or ""))
    skills = ", ".join(esc(item) for item in tailored_data.get("matching_skills", []))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>{esc(profile.name)} - Resume</title>
    <style>@page{{size:A4;margin:15mm}}body{{font:10pt Arial,sans-serif;color:#172033}}h1,h2{{margin-bottom:4pt}}.muted{{color:#475569}}</style>
    <h1>{esc(profile.name)}</h1><div class="muted">{esc(profile.title)}</div>
    <p>{esc(profile.email)} {esc(profile.phone)} {esc(profile.linkedin_url)} {esc(profile.github_url)} {esc(profile.portfolio_url)}</p>
    <h2>Professional Summary</h2><p>{esc(profile.summary)}</p>
    <h2>Skills</h2><p>{skills}</p></html>"""


class PDFResumeGenerator:
    """
    Generates tailored ATS resumes strictly grounded in verified candidate evidence.
    Always produces a canonical .tex LaTeX document and compiles it to PDF via Tectonic.
    """

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir or "tailored_resumes")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.last_generated_tex: Optional[Path] = None
        self.last_generated_pdf: Optional[Path] = None

    def generate_tex(
        self,
        profile: CandidateProfile,
        job: JobPosting,
        tailored_data: Dict[str, Any],
        filename: Optional[str] = None,
    ) -> Path:
        """
        Renders and writes the canonical .tex resume file preserving the Master CV template.
        """
        clean_company = re.sub(r"[^\w\-]", "_", job.company)
        clean_job_id = re.sub(r"[^\w\-]", "_", str(job.id))
        base_name = filename.replace(".pdf", "") if filename else f"resume_{clean_company}_{clean_job_id}"
        tex_path = self.output_dir / f"{base_name}.tex"

        tex_content = build_resume_latex(profile, job, tailored_data)
        tex_path.write_text(tex_content, encoding="utf-8")
        self.last_generated_tex = tex_path.resolve()
        logger.info(f"Wrote canonical LaTeX resume source at: {self.last_generated_tex}")
        return self.last_generated_tex

    def generate(
        self,
        profile: CandidateProfile,
        job: JobPosting,
        tailored_data: Dict[str, Any],
        filename: Optional[str] = None,
        force_latex: bool = True,
    ) -> Path:
        """
        Generates both .tex and .pdf files.
        Primary: Compiles .tex using local tectonic engine.
        Fallback: If tectonic is unavailable, compiles via Playwright headless Chromium.
        """
        # Step 1: Always generate the canonical .tex source file
        tex_path = self.generate_tex(profile, job, tailored_data, filename=filename)

        # Step 2: Attempt Tectonic compilation
        tectonic_bin = get_tectonic_path()
        if tectonic_bin:
            try:
                pdf_path = compile_latex_with_tectonic(tex_path, self.output_dir)
                self.last_generated_pdf = pdf_path
                logger.info(f"Generated tailored LaTeX vector PDF at: {pdf_path}")
                return pdf_path
            except Exception as e:
                logger.warning(f"Tectonic compilation failed ({e}), checking fallback...")
                if force_latex:
                    # If user strictly requires LaTeX and compilation failed, raise error
                    raise

        # Step 3: Fallback to Chromium headless PDF print if tectonic is missing
        logger.info("Using Playwright Chromium HTML-to-PDF fallback")
        from playwright.sync_api import sync_playwright

        clean_company = re.sub(r"[^\w\-]", "_", job.company)
        clean_job_id = re.sub(r"[^\w\-]", "_", str(job.id))
        pdf_name = filename if (filename and filename.endswith(".pdf")) else f"resume_{clean_company}_{clean_job_id}.pdf"
        out_path = self.output_dir / pdf_name

        html_content = build_resume_html(profile, job, tailored_data)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html_content, wait_until="load")
            page.pdf(
                path=str(out_path),
                format="A4",
                print_background=True,
                margin={"top": "10mm", "bottom": "10mm", "left": "13mm", "right": "13mm"},
            )
            browser.close()

        self.last_generated_pdf = out_path.resolve()
        logger.info(f"Generated fallback HTML PDF resume at: {self.last_generated_pdf}")
        return self.last_generated_pdf
