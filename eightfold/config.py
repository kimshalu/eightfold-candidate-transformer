import json
import re
from typing import List, Dict, Any, Optional

# Valid base fields on CanonicalRecord
VALID_BASE_FIELDS = {
    "candidate_id", "full_name", "emails", "phones", "location", "links",
    "headline", "years_experience", "skills", "experience", "education",
    "provenance", "overall_confidence", "possible_duplicate_of"
}

# Valid sub-fields for object types
VALID_SUBFIELDS = {
    "location": {"city", "region", "country"},
    "links": {"linkedin", "github", "portfolio", "other"},
    "skills[]": {"name", "confidence", "sources"},
    "experience[]": {"company", "title", "start", "end", "summary"},
    "education[]": {"institution", "degree", "field", "end_year"}
}

def validate_canonical_path(path: str) -> None:
    """
    Validates a canonical path. Raises ValueError if the path is invalid.
    Examples: 'emails[0]', 'location.city', 'skills[].name', 'full_name'
    """
    if not path:
        raise ValueError("Path cannot be empty")
        
    # Check simple base fields
    if path in VALID_BASE_FIELDS:
        return
        
    # Check indexed lists like emails[0], phones[0]
    m_idx = re.match(r'^(\w+)\[(\d+)\]$', path)
    if m_idx:
        base = m_idx.group(1)
        if base in ["emails", "phones"]:
            return
        raise ValueError(f"Invalid indexed list path: {path}. Only emails and phones support index access.")

    # Check list attribute projection like skills[].name
    m_list_proj = re.match(r'^(\w+)\[\]\.(\w+)$', path)
    if m_list_proj:
        base = m_list_proj.group(1)
        sub = m_list_proj.group(2)
        base_key = f"{base}[]"
        if base_key in VALID_SUBFIELDS and sub in VALID_SUBFIELDS[base_key]:
            return
        raise ValueError(f"Invalid list projection path: {path}. Field '{base}' or sub-field '{sub}' is not recognized.")

    # Check object path like location.city
    if '.' in path:
        parts = path.split('.')
        if len(parts) == 2:
            base, sub = parts[0], parts[1]
            if base in VALID_SUBFIELDS and sub in VALID_SUBFIELDS[base]:
                return
        raise ValueError(f"Invalid nested path: {path}. Nested path structure is unrecognized.")
        
    raise ValueError(f"Unknown canonical path: '{path}'")

class FieldConfig:
    def __init__(self, path: str, type_str: str, from_path: Optional[str] = None, required: bool = False, normalize: Optional[str] = None):
        self.path = path
        self.type_str = type_str
        self.from_path = from_path if from_path else path
        self.required = required
        self.normalize = normalize
        
        # Fail fast at load time
        validate_canonical_path(self.from_path)

class RuntimeConfig:
    def __init__(self, fields: List[FieldConfig], include_confidence: bool = True, include_provenance: bool = True, on_missing: str = "null"):
        self.fields = fields
        self.include_confidence = include_confidence
        self.include_provenance = include_provenance
        
        if on_missing not in ["null", "omit", "error"]:
            raise ValueError(f"Invalid on_missing policy: {on_missing}. Must be 'null', 'omit', or 'error'.")
        self.on_missing = on_missing

def load_config_from_dict(d: Dict[str, Any]) -> RuntimeConfig:
    """Parses a dictionary into a RuntimeConfig and validates it."""
    fields_data = d.get("fields", [])
    if not fields_data:
        # Default full fields config if empty
        fields_data = [
            {"path": "candidate_id", "type": "string"},
            {"path": "full_name", "type": "string"},
            {"path": "emails", "type": "string[]"},
            {"path": "phones", "type": "string[]"},
            {"path": "location", "type": "object"},
            {"path": "links", "type": "object"},
            {"path": "headline", "type": "string"},
            {"path": "years_experience", "type": "number"},
            {"path": "skills", "type": "object[]"},
            {"path": "experience", "type": "object[]"},
            {"path": "education", "type": "object[]"},
        ]
        
    fields = []
    for f in fields_data:
        fields.append(FieldConfig(
            path=f["path"],
            type_str=f["type"],
            from_path=f.get("from"),
            required=f.get("required", False),
            normalize=f.get("normalize")
        ))
        
    return RuntimeConfig(
        fields=fields,
        include_confidence=d.get("include_confidence", True),
        include_provenance=d.get("include_provenance", True),
        on_missing=d.get("on_missing", "null")
    )

def load_config_file(file_path: str) -> RuntimeConfig:
    """Loads a JSON config file and returns a RuntimeConfig."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return load_config_from_dict(data)
