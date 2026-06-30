from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class Location:
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None  # ISO-3166 alpha-2

@dataclass
class ExperienceEntry:
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None  # YYYY-MM
    end: Optional[str] = None    # YYYY-MM
    summary: Optional[str] = None

@dataclass
class EducationEntry:
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None

@dataclass
class ProvenanceEntry:
    field: str
    source_id: str
    source_type: str
    method: str
    value: Any
    confidence: float
    note: Optional[str] = None

@dataclass
class RawRecord:
    source_id: str
    source_type: str  # recruiter_csv, ats_json, resume, recruiter_notes
    method: str       # direct_field, regex_extract, heuristic_parse, derived
    
    full_name: Optional[str] = None
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    location: Optional[Location] = None
    links: Dict[str, Any] = field(default_factory=lambda: {
        "linkedin": None,
        "github": None,
        "portfolio": None,
        "other": []
    })
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[str] = field(default_factory=list)
    experience: List[ExperienceEntry] = field(default_factory=list)
    education: List[EducationEntry] = field(default_factory=list)

@dataclass
class SkillEntry:
    name: str
    confidence: float
    sources: List[str]

@dataclass
class CanonicalRecord:
    candidate_id: str
    full_name: Optional[str] = None
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    location: Optional[Location] = None
    links: Dict[str, Any] = field(default_factory=lambda: {
        "linkedin": None,
        "github": None,
        "portfolio": None,
        "other": []
    })
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[SkillEntry] = field(default_factory=list)
    experience: List[ExperienceEntry] = field(default_factory=list)
    education: List[EducationEntry] = field(default_factory=list)
    provenance: List[ProvenanceEntry] = field(default_factory=list)
    possible_duplicate_of: List[str] = field(default_factory=list)
    overall_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
