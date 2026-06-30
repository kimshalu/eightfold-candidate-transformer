import re
from datetime import datetime
from typing import Optional, Tuple, Dict
import phonenumbers

# Custom Country Mapper (ISO 3166 Alpha-2)
COUNTRY_MAP = {
    "united states": "US", "united states of america": "US", "usa": "US", "us": "US",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB", "gb": "GB",
    "india": "IN", "ind": "IN", "in": "IN",
    "canada": "CA", "can": "CA", "ca": "CA",
    "germany": "DE", "deutschland": "DE", "de": "DE",
    "france": "FR", "fra": "FR", "fr": "FR",
    "japan": "JP", "jpn": "JP", "jp": "JP",
    "australia": "AU", "aus": "AU", "au": "AU",
    "singapore": "SG", "sgp": "SG", "sg": "SG",
}

# Skills alias mapping: canonical_name -> list of aliases
SKILLS_ALIASES = {
    "react": ["reactjs", "react.js", "react-js", "react js"],
    "javascript": ["javascript", "js", "es6", "ecmascript"],
    "python": ["python", "py", "python3", "python 3"],
    "typescript": ["typescript", "ts"],
    "nodejs": ["node", "nodejs", "node.js", "node js"],
    "docker": ["docker", "dockerfile", "containers"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services", "ec2", "s3"],
    "c++": ["c++", "cpp", "c plus plus"],
    "postgresql": ["postgres", "postgresql", "pgsql"],
    "git": ["git", "github", "gitlab"],
    "django": ["django", "django framework"],
    "machine-learning": ["machine learning", "ml", "deep learning", "dl"],
    "nlp": ["nlp", "natural language processing"],
    "java": ["java", "jdk"],
}

# Flatten skills mapping for O(1) lookup
SKILLS_MAP: Dict[str, str] = {}
for canonical, aliases in SKILLS_ALIASES.items():
    for alias in aliases:
        SKILLS_MAP[alias.lower()] = canonical

def normalize_phone(phone_str: Optional[str], default_region: str = "US") -> Tuple[Optional[str], Optional[str]]:
    """
    Normalizes phone numbers to E.164 format.
    Returns (normalized_phone, note).
    If validation fails, returns (None, 'normalize_failed: ambiguous_region' or similar).
    """
    if not phone_str:
        return None, None
    
    # Strip basic non-digit/plus characters for preliminary cleaning
    cleaned = re.sub(r'[^\d+]', '', phone_str)
    if not cleaned:
        return None, "normalize_failed: invalid_format"
        
    try:
        # If number doesn't start with +, parser will use default_region
        parsed = phonenumbers.parse(phone_str, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164), None
        else:
            # Check if it could still parse but is invalid/ambiguous
            return None, "normalize_failed: ambiguous_region"
    except Exception as e:
        return None, f"normalize_failed: {str(e)}"

def normalize_date(date_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalizes a date string to YYYY-MM.
    If year-only, normalizes to YYYY-01 and returns note='precision: year'.
    Returns (normalized_date, note).
    """
    if not date_str:
        return None, None
    
    date_str = date_str.strip()
    
    # Check YYYY-only format
    if re.match(r'^\d{4}$', date_str):
        return f"{date_str}-01", "precision: year"
        
    # Check YYYY-MM or YYYY/MM
    m = re.match(r'^(\d{4})[-/](\d{2})$', date_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}", None
        
    # Try custom textual parsing like "May 2020", "2020 May", etc.
    # Month list
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    month_map = {m: i+1 for i, m in enumerate(months)}
    
    # Lowercase for match
    date_lower = date_str.lower()
    
    # Look for a 4-digit year
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', date_str)
    if not year_match:
        return None, "normalize_failed: no_valid_year"
        
    year = year_match.group(1)
    
    # Look for a month name
    found_month = None
    for m_name, m_val in month_map.items():
        if m_name in date_lower:
            found_month = f"{m_val:02d}"
            break
            
    if found_month:
        return f"{year}-{found_month}", None
        
    # Fallback to year-only if we found a year but no month
    return f"{year}-01", "precision: year"

def normalize_country(country_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalizes country to ISO-3166 alpha-2 format.
    Returns (iso_code, note).
    """
    if not country_str:
        return None, None
        
    cleaned = country_str.strip().lower()
    if cleaned in COUNTRY_MAP:
        return COUNTRY_MAP[cleaned], None
        
    # If already a valid 2-letter uppercase country code (lenient check)
    if len(country_str.strip()) == 2 and country_str.strip().isupper():
        return country_str.strip(), None
        
    return None, "normalize_failed: unknown_country"

def normalize_skill(skill_str: str) -> str:
    """
    Normalizes skill string using custom canonical map.
    If no alias is matched, returns lowercase stripped skill string.
    """
    cleaned = skill_str.strip().lower()
    return SKILLS_MAP.get(cleaned, cleaned)
