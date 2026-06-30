from typing import List, Dict, Any, Optional, Tuple, Set
import uuid
import logging
from datetime import datetime

from eightfold.models import (
    RawRecord, CanonicalRecord, Location, ExperienceEntry, 
    EducationEntry, ProvenanceEntry, SkillEntry
)
from eightfold.pipeline.normalize import (
    normalize_phone, normalize_date, normalize_country, normalize_skill
)

logger = logging.getLogger("eightfold.merge")

# Trust and Confidence Weights
SOURCE_TRUST = {
    'recruiter_csv': 0.90,
    'ats_json': 0.85,
    'resume': 0.75,
    'recruiter_notes': 0.55
}

# NOTE: kept in sync with the design doc's stated weights
# (direct_field / regex_extract / heuristic_parse / derived).
# `derived` is intentionally the second-highest weight (not the highest) —
# a computed value (e.g. date-math years_experience) should usually beat a
# stated free-text claim, but should not automatically outrank a direct_field
# value from a trusted structured source.
METHOD_CONFIDENCE = {
    'direct_field': 1.0,
    'regex_extract': 0.70,
    'heuristic_parse': 0.65,
    'derived': 0.80
}

import re

def clean_string(s: Optional[str]) -> str:
    """Helper to lowercase, strip punctuation and company suffixes."""
    if not s:
        return ""
    s = re.sub(r'\b(inc|corp|co|ltd|llc|limited|corporation)\b', '', s.lower())
    return re.sub(r'[^a-z0-9]', '', s)

def get_confidence(source_type: str, method: str) -> float:
    trust = SOURCE_TRUST.get(source_type, 0.50)
    method_val = METHOD_CONFIDENCE.get(method, 0.50)
    return round(trust * method_val, 3)

def compute_experience_years(start_str: Optional[str], end_str: Optional[str]) -> float:
    """Computes years of experience between two normalized date strings (YYYY-MM)."""
    if not start_str:
        return 0.0
        
    try:
        start_norm, _ = normalize_date(start_str)
        if not start_norm:
            return 0.0
        start_dt = datetime.strptime(start_norm, "%Y-%m")
        
        if not end_str or end_str.lower() in ["present", "current", "now"]:
            end_dt = datetime.now()
        else:
            end_norm, _ = normalize_date(end_str)
            if not end_norm:
                end_dt = datetime.now()
            else:
                end_dt = datetime.strptime(end_norm, "%Y-%m")
                
        diff_days = (end_dt - start_dt).days
        years = max(0.0, diff_days / 365.25)
        return round(years, 1)
    except Exception:
        return 0.0

def merge_cluster(records: List[RawRecord], default_region: str = "US") -> CanonicalRecord:
    """
    Merges a list of RawRecord objects representing the same person into a single CanonicalRecord.
    Tracks provenance and scores field-level confidence.

    Note: `possible_duplicate_of` is intentionally NOT set here. It is populated
    by the orchestration layer (cli.py / run_pipeline) after all clusters have been
    merged and final candidate_ids are known, since it references OTHER candidates'
    ids, which don't exist yet at the point a single cluster is being merged.
    """
    candidate_id = f"cand_{uuid.uuid4().hex[:12]}"
    
    all_provenance: List[ProvenanceEntry] = []
    
    names_proposed: Dict[str, List[Tuple[RawRecord, str, float]]] = {}
    emails_proposed: Dict[str, List[Tuple[RawRecord, str, float]]] = {}
    phones_proposed: Dict[str, List[Tuple[RawRecord, str, float, Optional[str]]]] = {}
    headlines_proposed: Dict[str, List[Tuple[RawRecord, str, float]]] = {}
    years_exp_proposed: Dict[float, List[Tuple[RawRecord, Any, float, str]]] = {}
    
    cities_proposed: Dict[str, List[Tuple[RawRecord, str, float]]] = {}
    regions_proposed: Dict[str, List[Tuple[RawRecord, str, float]]] = {}
    countries_proposed: Dict[str, List[Tuple[RawRecord, str, float, Optional[str]]]] = {}
    
    links_proposed: Dict[str, Dict[str, List[Tuple[RawRecord, str, float]]]] = {
        "linkedin": {}, "github": {}, "portfolio": {}, "other": {}
    }
    
    skills_proposed: Dict[str, List[Tuple[RawRecord, str, float]]] = {}
    
    exp_entries_raw: List[Tuple[RawRecord, ExperienceEntry, float]] = []
    edu_entries_raw: List[Tuple[RawRecord, EducationEntry, float]] = []
    
    for r in records:
        base_confidence = get_confidence(r.source_type, r.method)
        
        if r.full_name:
            norm_name = r.full_name.strip()
            if norm_name:
                names_proposed.setdefault(norm_name, []).append((r, r.full_name, base_confidence))
                
        for email in r.emails:
            if email and email.strip():
                norm_email = email.strip().lower()
                emails_proposed.setdefault(norm_email, []).append((r, email, base_confidence))
                
        for phone in r.phones:
            if phone and phone.strip():
                norm_p, p_note = normalize_phone(phone, default_region)
                val_key = norm_p if norm_p else f"normalize_failed_{phone}"
                phones_proposed.setdefault(val_key, []).append((r, phone, base_confidence, p_note))
                
        if r.headline:
            norm_hl = r.headline.strip()
            headlines_proposed.setdefault(norm_hl, []).append((r, r.headline, base_confidence))
            
        if r.years_experience is not None:
            years_exp_proposed.setdefault(r.years_experience, []).append((r, r.years_experience, base_confidence, r.method))
            
        computed_years = 0.0
        for exp in r.experience:
            computed_years += compute_experience_years(exp.start, exp.end)
        if computed_years > 0:
            computed_years = round(computed_years, 1)
            derived_conf = get_confidence(r.source_type, 'derived')
            years_exp_proposed.setdefault(computed_years, []).append((r, f"Computed from experience: {computed_years}", derived_conf, 'derived'))
            
        if r.location:
            if r.location.city:
                norm_city = r.location.city.strip()
                cities_proposed.setdefault(norm_city, []).append((r, r.location.city, base_confidence))
            if r.location.region:
                norm_region = r.location.region.strip()
                regions_proposed.setdefault(norm_region, []).append((r, r.location.region, base_confidence))
            if r.location.country:
                norm_c, c_note = normalize_country(r.location.country)
                val_key = norm_c if norm_c else f"normalize_failed_{r.location.country}"
                countries_proposed.setdefault(val_key, []).append((r, r.location.country, base_confidence, c_note))
                
        for ltype in ["linkedin", "github", "portfolio"]:
            lval = r.links.get(ltype)
            if lval:
                norm_l = lval.strip()
                links_proposed[ltype].setdefault(norm_l, []).append((r, lval, base_confidence))
        for lval in r.links.get("other", []):
            if lval:
                norm_l = lval.strip()
                links_proposed["other"].setdefault(norm_l, []).append((r, lval, base_confidence))
                
        for skill in r.skills:
            norm_sk = normalize_skill(skill)
            skills_proposed.setdefault(norm_sk, []).append((r, skill, base_confidence))
            
        for exp in r.experience:
            exp_entries_raw.append((r, exp, base_confidence))
            
        for edu in r.education:
            edu_entries_raw.append((r, edu, base_confidence))

    def resolve_field(field_name: str, proposed_dict: Dict[Any, List[Tuple[RawRecord, Any, float]]], is_phone_or_country: bool = False) -> Tuple[Optional[Any], float]:
        if not proposed_dict:
            return None, 0.0
            
        best_val = None
        best_conf = -1.0
        
        for val, prop_list in proposed_dict.items():
            if isinstance(val, str) and "normalize_failed" in val:
                for rec, orig, conf, note in prop_list:
                    all_provenance.append(ProvenanceEntry(
                        field=field_name,
                        source_id=rec.source_id,
                        source_type=rec.source_type,
                        method=rec.method,
                        value=None,
                        confidence=conf,
                        note=note
                    ))
                continue
                
            max_base_conf = max(item[2] for item in prop_list)
            agreeing_sources = len(set(item[0].source_id for item in prop_list))
            corrob_boost = 0.05 * (agreeing_sources - 1)
            final_conf = min(1.0, round(max_base_conf + corrob_boost, 3))
            
            if final_conf > best_conf:
                best_conf = final_conf
                best_val = val
                
        for val, prop_list in proposed_dict.items():
            is_winner = (val == best_val)
            for item in prop_list:
                rec, orig, conf = item[0], item[1], item[2]
                note = item[3] if len(item) > 3 else None
                
                if field_name.endswith('.start') or field_name.endswith('.end') or field_name == 'education.end_year':
                    _, d_note = normalize_date(str(orig))
                    if d_note:
                        note = d_note
                        
                all_provenance.append(ProvenanceEntry(
                    field=field_name,
                    source_id=rec.source_id,
                    source_type=rec.source_type,
                    method=item[3] if field_name == 'years_experience' and len(item) > 3 else rec.method,
                    value=val if "normalize_failed" not in str(val) else None,
                    confidence=conf,
                    note=note
                ))
                
        return best_val, best_conf

    final_full_name, name_conf = resolve_field("full_name", names_proposed)
    final_headline, headline_conf = resolve_field("headline", headlines_proposed)
    
    years_exp_proposed_cast = {k: [(item[0], item[1], item[2]) for item in v] for k, v in years_exp_proposed.items()}
    final_years_exp, exp_conf = resolve_field("years_experience", years_exp_proposed_cast)

    final_city, city_conf = resolve_field("location.city", cities_proposed)
    final_region, region_conf = resolve_field("location.region", regions_proposed)
    
    countries_proposed_cast = {k: [(item[0], item[1], item[2], item[3]) for item in v] for k, v in countries_proposed.items()}
    final_country, country_conf = resolve_field("location.country", countries_proposed_cast)
    
    final_location = None
    if final_city or final_region or final_country:
        final_location = Location(city=final_city, region=final_region, country=final_country)

    final_emails: List[str] = []
    email_confs: List[float] = []
    for email, prop_list in emails_proposed.items():
        max_base_conf = max(item[2] for item in prop_list)
        agreeing_sources = len(set(item[0].source_id for item in prop_list))
        final_conf = min(1.0, round(max_base_conf + 0.05 * (agreeing_sources - 1), 3))
        
        final_emails.append(email)
        email_confs.append(final_conf)
        
        for rec, orig, conf in prop_list:
            all_provenance.append(ProvenanceEntry(
                field="emails",
                source_id=rec.source_id,
                source_type=rec.source_type,
                method=rec.method,
                value=email,
                confidence=conf
            ))

    final_phones: List[str] = []
    phone_confs: List[float] = []
    for val_key, prop_list in phones_proposed.items():
        if "normalize_failed" in val_key:
            for rec, orig, conf, note in prop_list:
                all_provenance.append(ProvenanceEntry(
                    field="phones",
                    source_id=rec.source_id,
                    source_type=rec.source_type,
                    method=rec.method,
                    value=None,
                    confidence=conf,
                    note=note
                ))
            continue
            
        max_base_conf = max(item[2] for item in prop_list)
        agreeing_sources = len(set(item[0].source_id for item in prop_list))
        final_conf = min(1.0, round(max_base_conf + 0.05 * (agreeing_sources - 1), 3))
        
        final_phones.append(val_key)
        phone_confs.append(final_conf)
        
        for rec, orig, conf, note in prop_list:
            all_provenance.append(ProvenanceEntry(
                field="phones",
                source_id=rec.source_id,
                source_type=rec.source_type,
                method=rec.method,
                value=val_key,
                confidence=conf,
                note=note
            ))

    final_links = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    link_confs: List[float] = []
    
    for ltype in ["linkedin", "github", "portfolio"]:
        prop_l = links_proposed[ltype]
        if prop_l:
            best_l, l_conf = resolve_field(f"links.{ltype}", prop_l)
            final_links[ltype] = best_l
            link_confs.append(l_conf)
            
    for lval, prop_list in links_proposed["other"].items():
        max_base_conf = max(item[2] for item in prop_list)
        agreeing_sources = len(set(item[0].source_id for item in prop_list))
        final_conf = min(1.0, round(max_base_conf + 0.05 * (agreeing_sources - 1), 3))
        
        final_links["other"].append(lval)
        link_confs.append(final_conf)
        for rec, orig, conf in prop_list:
            all_provenance.append(ProvenanceEntry(
                field="links.other",
                source_id=rec.source_id,
                source_type=rec.source_type,
                method=rec.method,
                value=lval,
                confidence=conf
            ))

    final_skills: List[SkillEntry] = []
    skill_confs: List[float] = []
    for skill_name, prop_list in skills_proposed.items():
        max_base_conf = max(item[2] for item in prop_list)
        agreeing_sources = len(set(item[0].source_id for item in prop_list))
        final_conf = min(1.0, round(max_base_conf + 0.05 * (agreeing_sources - 1), 3))
        
        sources_list = list(set(item[0].source_id for item in prop_list))
        final_skills.append(SkillEntry(
            name=skill_name,
            confidence=final_conf,
            sources=sources_list
        ))
        skill_confs.append(final_conf)
        
        for rec, orig, conf in prop_list:
            all_provenance.append(ProvenanceEntry(
                field="skills",
                source_id=rec.source_id,
                source_type=rec.source_type,
                method=rec.method,
                value=skill_name,
                confidence=conf
            ))

    exp_groups: Dict[str, List[Tuple[RawRecord, ExperienceEntry, float]]] = {}
    for rec, exp, conf in exp_entries_raw:
        c_comp = clean_string(exp.company)
        if c_comp:
            exp_groups.setdefault(c_comp, []).append((rec, exp, conf))
            
    final_experience: List[ExperienceEntry] = []
    exp_item_confs: List[float] = []
    for c_comp, prop_list in exp_groups.items():
        best_item = max(prop_list, key=lambda x: x[2])
        best_exp = best_item[1]
        
        titles = {}
        start_dates = {}
        end_dates = {}
        summaries = {}
        for rec, exp, conf in prop_list:
            if exp.title:
                titles.setdefault(exp.title, []).append((rec, exp.title, conf))
            if exp.start:
                start_dates.setdefault(exp.start, []).append((rec, exp.start, conf))
            if exp.end:
                end_dates.setdefault(exp.end, []).append((rec, exp.end, conf))
            if exp.summary:
                summaries.setdefault(exp.summary, []).append((rec, exp.summary, conf))
                
        resolved_title, title_conf = resolve_field("experience.title", titles)
        resolved_start, start_conf = resolve_field("experience.start", start_dates)
        resolved_end, end_conf = resolve_field("experience.end", end_dates)
        resolved_summary, sum_conf = resolve_field("experience.summary", summaries)
        
        max_base_conf = max(item[2] for item in prop_list)
        agreeing_sources = len(set(item[0].source_id for item in prop_list))
        final_conf = min(1.0, round(max_base_conf + 0.05 * (agreeing_sources - 1), 3))
        
        norm_start, _ = normalize_date(resolved_start)
        norm_end, _ = normalize_date(resolved_end)
        
        final_experience.append(ExperienceEntry(
            company=best_exp.company,
            title=resolved_title or best_exp.title,
            start=norm_start or resolved_start,
            end=norm_end or resolved_end,
            summary=resolved_summary
        ))
        exp_item_confs.append(final_conf)
        
        for rec, exp, conf in prop_list:
            all_provenance.append(ProvenanceEntry(
                field="experience",
                source_id=rec.source_id,
                source_type=rec.source_type,
                method=rec.method,
                value={"company": exp.company, "title": exp.title, "start": exp.start, "end": exp.end},
                confidence=conf
            ))

    edu_groups: Dict[Tuple[str, str], List[Tuple[RawRecord, EducationEntry, float]]] = {}
    for rec, edu, conf in edu_entries_raw:
        c_inst = clean_string(edu.institution)
        c_deg = clean_string(edu.degree)
        if c_inst or c_deg:
            edu_groups.setdefault((c_inst, c_deg), []).append((rec, edu, conf))
            
    final_education: List[EducationEntry] = []
    edu_item_confs: List[float] = []
    for (c_inst, c_deg), prop_list in edu_groups.items():
        best_item = max(prop_list, key=lambda x: x[2])
        best_edu = best_item[1]
        
        fields = {}
        end_years = {}
        for rec, edu, conf in prop_list:
            if edu.field:
                fields.setdefault(edu.field, []).append((rec, edu.field, conf))
            if edu.end_year is not None:
                end_years.setdefault(edu.end_year, []).append((rec, edu.end_year, conf))
                
        resolved_field_name, field_conf = resolve_field("education.field", fields)
        resolved_end_year, end_yr_conf = resolve_field("education.end_year", end_years)
        
        max_base_conf = max(item[2] for item in prop_list)
        agreeing_sources = len(set(item[0].source_id for item in prop_list))
        final_conf = min(1.0, round(max_base_conf + 0.05 * (agreeing_sources - 1), 3))
        
        final_education.append(EducationEntry(
            institution=best_edu.institution,
            degree=best_edu.degree,
            field=resolved_field_name,
            end_year=resolved_end_year
        ))
        edu_item_confs.append(final_conf)
        
        for rec, edu, conf in prop_list:
            all_provenance.append(ProvenanceEntry(
                field="education",
                source_id=rec.source_id,
                source_type=rec.source_type,
                method=rec.method,
                value={"institution": edu.institution, "degree": edu.degree, "field": edu.field, "end_year": edu.end_year},
                confidence=conf
            ))

    populated_confs: List[float] = []
    if final_full_name:
        populated_confs.append(name_conf)
    if final_emails:
        populated_confs.extend(email_confs)
    if final_phones:
        populated_confs.extend(phone_confs)
    if final_location:
        if final_city:
            populated_confs.append(city_conf)
        if final_region:
            populated_confs.append(region_conf)
        if final_country:
            populated_confs.append(country_conf)
    if final_headline:
        populated_confs.append(headline_conf)
    if final_years_exp is not None:
        populated_confs.append(exp_conf)
    if final_skills:
        populated_confs.extend(skill_confs)
    if final_experience:
        populated_confs.extend(exp_item_confs)
    if final_education:
        populated_confs.extend(edu_item_confs)
        
    overall_conf = 0.0
    if populated_confs:
        overall_conf = round(sum(populated_confs) / len(populated_confs), 3)

    return CanonicalRecord(
        candidate_id=candidate_id,
        full_name=final_full_name,
        emails=final_emails,
        phones=final_phones,
        location=final_location,
        links=final_links,
        headline=final_headline,
        years_experience=final_years_exp,
        skills=final_skills,
        experience=final_experience,
        education=final_education,
        provenance=all_provenance,
        overall_confidence=overall_conf,
        possible_duplicate_of=[]  # populated later by cli.py once all candidate_ids are known
    )
    