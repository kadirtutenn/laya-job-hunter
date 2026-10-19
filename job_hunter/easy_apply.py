"""
Automated Application Agent (Easy Apply & Form Filling):
Fills multi-step application forms (LinkedIn Easy Apply, Greenhouse, Lever)
using candidate profile data, tailored resume uploads, and Laya decisions for screening questions.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting

logger = logging.getLogger(__name__)


class EasyApplyAgent:
    """Fills multi-step application forms deterministically with Laya screening decisions."""

    def __init__(self, laya_client: LayaClient, auto_submit: bool = False):
        self.client = laya_client
        self.auto_submit = auto_submit

    def fill_form_step(
        self,
        page: Any,
        profile: CandidateProfile,
        resume_pdf_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Inspects the current form modal/page and fills all detected inputs,
        answers screening questions with Laya, and uploads resume if requested.
        """
        filled_fields = []
        answered_questions = []

        # 1. Fill Text Inputs
        inputs = page.query_selector_all('input[type="text"], input[type="tel"], input[type="email"], input[type="number"], textarea')
        for inp in inputs:
            try:
                if not inp.is_visible() or inp.get_attribute("readonly") or inp.get_attribute("disabled"):
                    continue

                # Get existing value
                val = inp.input_value()
                if val and len(val.strip()) > 1:
                    continue  # Already filled

                label_text = self._get_input_label(page, inp).lower()
                name_attr = (inp.get_attribute("name") or "").lower()
                id_attr = (inp.get_attribute("id") or "").lower()
                combined = f"{label_text} {name_attr} {id_attr}"

                # Match field semantics
                if any(k in combined for k in ["phone", "mobile", "tel", "telefon"]) and profile.phone:
                    inp.fill(profile.phone)
                    filled_fields.append("phone")
                elif any(k in combined for k in ["email", "e-posta"]) and profile.email:
                    inp.fill(profile.email)
                    filled_fields.append("email")
                elif any(k in combined for k in ["first name", "adınız"]):
                    first = profile.name.split()[0]
                    inp.fill(first)
                    filled_fields.append("first_name")
                elif any(k in combined for k in ["last name", "soyadınız"]):
                    last = profile.name.split()[-1] if len(profile.name.split()) > 1 else ""
                    inp.fill(last)
                    filled_fields.append("last_name")
                elif any(k in combined for k in ["full name", "ad soyad", "name"]):
                    inp.fill(profile.name)
                    filled_fields.append("full_name")
                elif any(k in combined for k in ["city", "location", "şehir", "konum"]) and profile.preferred_locations:
                    inp.fill(profile.preferred_locations[0])
                    filled_fields.append("location")
                elif any(k in combined for k in ["linkedin"]):
                    inp.fill(profile.linkedin_url)
                    filled_fields.append("linkedin")
                elif any(k in combined for k in ["github"]):
                    inp.fill(profile.github_url)
                    filled_fields.append("github")
                elif any(k in combined for k in ["website", "portfolio", "blog"]):
                    inp.fill(profile.portfolio_url)
                    filled_fields.append("portfolio")
                elif any(k in combined for k in ["years of experience", "deneyim yılı", "how many years"]) and profile.min_years_experience > 0:
                    inp.fill(str(profile.min_years_experience))
                    filled_fields.append("years_experience")
            except Exception as e:
                logger.debug(f"Input fill error: {e}")

        # 2. Answer Screening Questions (Radio Buttons & Select Dropdowns via Laya)
        fieldsets = page.query_selector_all('fieldset, [data-test-form-builder-radio-button-form-component]')
        for fs in fieldsets:
            try:
                legend = fs.query_selector('legend, label, .fb-dash-form-element__label')
                q_text = legend.inner_text().strip() if legend else ""
                if not q_text:
                    continue

                radios = fs.query_selector_all('input[type="radio"]')
                if not radios:
                    continue

                # Check if already selected
                is_selected = any(r.is_checked() for r in radios)
                if is_selected:
                    continue

                options = {}
                radio_map = {}
                for idx, r in enumerate(radios):
                    label_el = fs.query_selector(f'label[for="{r.get_attribute("id")}"]') or r.evaluate_handle('el => el.closest("label") or el.parentElement')
                    label_str = label_el.inner_text().strip() if label_el else f"Option {idx}"
                    key = f"opt_{idx}"
                    options[key] = label_str
                    radio_map[key] = r

                # Screening questions may ask about work authorization, sponsorship,
                # compensation, or other sensitive facts. Leave them for the user.
                if len(options) >= 2:
                    answered_questions.append({"question": q_text[:120], "choice": "user input required"})
            except Exception as e:
                logger.debug(f"Radio question error: {e}")

        # 3. Handle File Upload (Resume PDF)
        if resume_pdf_path and Path(resume_pdf_path).exists():
            file_input = page.query_selector('input[type="file"]')
            if file_input and file_input.is_visible():
                try:
                    file_input.set_input_files(str(Path(resume_pdf_path).resolve()))
                    filled_fields.append("resume_upload")
                    logger.info(f"Attached tailored resume: {resume_pdf_path}")
                except Exception as e:
                    logger.warning(f"Failed attaching resume: {e}")

        return {
            "filled_fields": filled_fields,
            "answered_questions": answered_questions,
        }

    def _decide_screening_answer(self, profile: CandidateProfile, question: str, options: Dict[str, str]) -> Optional[str]:
        """Never guesses screening answers; the user must answer them."""
        return None

    def _get_input_label(self, page: Any, inp: Any) -> str:
        """Finds the label associated with an input."""
        inp_id = inp.get_attribute("id")
        if inp_id:
            label = page.query_selector(f'label[for="{inp_id}"]')
            if label:
                return label.inner_text().strip()

        parent_label = inp.evaluate_handle('el => el.closest("label")')
        if parent_label and hasattr(parent_label, "inner_text"):
            try:
                return parent_label.inner_text().strip()
            except Exception:
                pass

        placeholder = inp.get_attribute("placeholder") or ""
        aria_label = inp.get_attribute("aria-label") or ""
        return placeholder or aria_label
