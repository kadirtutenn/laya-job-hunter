"""Small evidence-based LaTeX helpers for candidate supplied content."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from typing import Optional

TECTONIC_CANDIDATES = [shutil.which("tectonic"), "/opt/homebrew/bin/tectonic", "/usr/local/bin/tectonic", Path.home() / ".cargo/bin/tectonic"]

def get_tectonic_path() -> Optional[str]:
    for candidate in TECTONIC_CANDIDATES:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None

def escape_latex(text) -> str:
    if text is None:
        return ""
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(char, char) for char in str(text))

def build_resume_latex(profile, job, tailored_data):
    """Create a minimal resume from explicitly supplied profile fields only."""
    if not profile.name or not profile.title or not profile.summary:
        raise ValueError("Complete your local profile with facts supported by your CV before generating a resume.")
    skills = ", ".join(escape_latex(item) for item in tailored_data.get("matching_skills", []))
    if not skills:
        skills = ", ".join(escape_latex(item) for item in profile.core_skills)
    contact = " | ".join(escape_latex(value) for value in (profile.email, profile.phone, profile.linkedin_url, profile.github_url, profile.portfolio_url) if value)
    return rf"\documentclass[10pt,a4paper]{{article}}
\usepackage[margin=18mm]{{geometry}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern}}
\begin{{document}}
\begin{{center}}{{\LARGE\bfseries {escape_latex(profile.name)}}}\\{escape_latex(profile.title)}\\{contact}\end{{center}}
\section*{{Professional Summary}}{escape_latex(profile.summary)}
\section*{{Skills}}{skills}\end{{document}}"

def compile_latex_with_tectonic(tex_path, output_dir):
    binary = get_tectonic_path()
    if not binary:
        raise FileNotFoundError("Tectonic is not installed")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([binary, str(tex_path), "--outdir", str(out_dir)], check=True)
    return out_dir / (Path(tex_path).stem + ".pdf")
