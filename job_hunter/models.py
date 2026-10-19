from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class CandidateProfile:
    """A candidate profile. Empty defaults prevent accidental use of another person's data."""
    name: str = ""
    title: str = ""
    summary: str = ""
    core_skills: List[str] = field(default_factory=list)
    preferred_roles: List[str] = field(default_factory=list)
    preferred_locations: List[str] = field(default_factory=list)
    min_years_experience: int = 0
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    dealbreakers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CandidateProfile:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class JobPosting:
    title: str
    company: str
    location: str
    url: str
    description: str
    id: str = ""
    tags: List[str] = field(default_factory=list)
    source: str = "web"
    has_easy_apply: bool = False
    discovered_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.id:
            import re
            m = re.search(r'(\d{8,12})', self.url)
            if m:
                clean_key = f"job:{m.group(1)}"
            else:
                clean_key = f"{self.company.lower().strip()}:{self.title.lower().strip()}"
            self.id = hashlib.sha256(clean_key.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> JobPosting:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MatchReport:
    fit_score: float  # 0.0 to 1.0 (calibrated percentage)
    fit_level: str  # "poor", "partial", "strong", "perfect"
    seniority_fit: str  # "underqualified", "matched", "overqualified"
    tech_stack_fit: str  # "missing_critical", "partial_overlap", "exact_match"
    should_apply: bool
    should_apply_prob: float  # 0.0 to 1.0
    confidence: float
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MatchReport:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ValidationResult:
    is_valid: bool
    reasons: List[str] = field(default_factory=list)
    dealbreakers_triggered: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ValidationResult:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CultureReport:
    company: str
    culture_score: float  # 0.0 to 1.0 (calibrated company rating)
    work_life_balance_signal: str  # "high", "moderate", "challenging"
    tech_debt_risk: str  # "low", "medium", "high"
    engineering_autonomy: str  # "high_autonomy", "moderate", "hierarchical"
    highlights: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    estimated_salary_range: str = "Market Competitive"
    github_signals: Dict[str, Any] = field(default_factory=dict)
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CultureReport:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class EmailEvent:
    id: str
    subject: str
    sender: str
    body_snippet: str
    category: str  # "interview_invitation", "assessment_test", "screening_call", "application_received", "rejection", "irrelevant"
    matched_job_id: Optional[str] = None
    matched_company: Optional[str] = None
    confidence: float = 0.0
    action_taken: str = ""
    received_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EmailEvent:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class OutreachStep:
    id: str
    job_id: str
    step_day: int  # 0 (Day 0), 5 (Day 5), 12 (Day 12)
    channel: str  # "linkedin", "email"
    subject: str
    body: str
    status: str = "draft"  # "draft", "approved", "sent"
    scheduled_for: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OutreachStep:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ScoredJob:
    job: JobPosting
    match: MatchReport
    validation: ValidationResult
    status: str = "inbox"  # "inbox", "shortlisted", "archived", "applied", "interview_scheduled", "assessment", "rejected"
    notes: str = ""
    culture: Optional[CultureReport] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job": self.job.to_dict(),
            "match": self.match.to_dict(),
            "validation": self.validation.to_dict(),
            "status": self.status,
            "notes": self.notes,
            "culture": self.culture.to_dict() if self.culture else None,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScoredJob:
        culture_data = data.get("culture")
        culture_obj = CultureReport.from_dict(culture_data) if culture_data else None
        return cls(
            job=JobPosting.from_dict(data["job"]),
            match=MatchReport.from_dict(data["match"]),
            validation=ValidationResult.from_dict(data["validation"]),
            status=data.get("status", "inbox"),
            notes=data.get("notes", ""),
            culture=culture_obj,
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )
