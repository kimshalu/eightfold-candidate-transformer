import re
from typing import Any, Dict, List, Optional
from eightfold.models import CanonicalRecord, SkillEntry
from eightfold.config import RuntimeConfig, FieldConfig
from eightfold.pipeline.normalize import normalize_phone, normalize_skill, normalize_country

def evaluate_path(record: CanonicalRecord, path: str) -> Any:
    """
    Evaluates a path string against a CanonicalRecord object.
    Supports simple paths, indexed list paths (e.g., emails[0]),
    object paths (e.g., location.city), and list projections (e.g., skills[].name).
    """
    if path == "candidate_id":
        return record.candidate_id
    elif path == "full_name":
        return record.full_name
    elif path == "emails":
        return record.emails
    elif path == "phones":
        return record.phones
    elif path == "location":
        return record.location
    elif path == "links":
        return record.links
    elif path == "headline":
        return record.headline
    elif path == "years_experience":
        return record.years_experience
    elif path == "skills":
        return record.skills
    elif path == "experience":
        return record.experience
    elif path == "education":
        return record.education
    elif path == "provenance":
        return record.provenance
    elif path == "overall_confidence":
        return record.overall_confidence
    elif path == "possible_duplicate_of":
        return record.possible_duplicate_of

    # 1. Indexed access: e.g. emails[0]
    m_idx = re.match(r'^(\w+)\[(\d+)\]$', path)
    if m_idx:
        base = m_idx.group(1)
        idx = int(m_idx.group(2))
        list_val = getattr(record, base, None)
        if list_val and isinstance(list_val, list) and idx < len(list_val):
            return list_val[idx]
        return None

    # 2. List attribute projection: e.g. skills[].name
    m_list_proj = re.match(r'^(\w+)\[\]\.(\w+)$', path)
    if m_list_proj:
        base = m_list_proj.group(1)
        sub = m_list_proj.group(2)
        list_val = getattr(record, base, None)
        if list_val and isinstance(list_val, list):
            res = []
            for item in list_val:
                # item can be a dataclass or a dict
                if hasattr(item, sub):
                    val = getattr(item, sub)
                elif isinstance(item, dict):
                    val = item.get(sub)
                else:
                    val = None
                if val is not None:
                    res.append(val)
            return res
        return []

    # 3. Object nested path: e.g. location.city, links.linkedin
    if '.' in path:
        parts = path.split('.')
        base = parts[0]
        sub = parts[1]
        base_val = getattr(record, base, None)
        if base_val:
            if hasattr(base_val, sub):
                return getattr(base_val, sub)
            elif isinstance(base_val, dict):
                return base_val.get(sub)
        return None

    return None

def apply_normalization(val: Any, norm_type: Optional[str]) -> Any:
    """Applies normalization override to value."""
    if not val or not norm_type:
        return val
        
    norm_type_lower = norm_type.lower()
    
    if isinstance(val, list):
        # Normalize elements in list
        normalized_list = []
        for x in val:
            if norm_type_lower in ["e164", "phone"]:
                norm_x, _ = normalize_phone(str(x))
                normalized_list.append(norm_x or x)
            elif norm_type_lower in ["canonical", "skill"]:
                normalized_list.append(normalize_skill(str(x)))
            elif norm_type_lower in ["country", "iso3166"]:
                norm_x, _ = normalize_country(str(x))
                normalized_list.append(norm_x or x)
            else:
                normalized_list.append(x)
        return normalized_list
    else:
        # Normalize scalar
        if norm_type_lower in ["e164", "phone"]:
            norm_val, _ = normalize_phone(str(val))
            return norm_val or val
        elif norm_type_lower in ["canonical", "skill"]:
            return normalize_skill(str(val))
        elif norm_type_lower in ["country", "iso3166"]:
            norm_val, _ = normalize_country(str(val))
            return norm_val or val
            
    return val

def type_check(val: Any, type_str: str) -> bool:
    """Checks if value conforms to the declared type string in config."""
    if val is None:
        return True
        
    type_str = type_str.strip().lower()
    
    if type_str == "string":
        return isinstance(val, str)
    elif type_str == "number":
        return isinstance(val, (int, float))
    elif type_str == "boolean":
        return isinstance(val, bool)
    elif type_str == "object":
        return isinstance(val, dict)
    elif type_str == "string[]":
        return isinstance(val, list) and all(isinstance(x, str) for x in val)
    elif type_str == "number[]":
        return isinstance(val, list) and all(isinstance(x, (int, float)) for x in val)
    elif type_str == "object[]":
        return isinstance(val, list) and all(isinstance(x, dict) for x in val)
        
    # Default fallback
    return True

def project_record(record: CanonicalRecord, config: RuntimeConfig) -> Dict[str, Any]:
    """
    Projects a CanonicalRecord into a output dictionary based on the RuntimeConfig.
    Applies required checks, normalization, type checks, missing policies, and metadata toggles.
    """
    output: Dict[str, Any] = {}
    
    for f in config.fields:
        raw_val = evaluate_path(record, f.from_path)
        
        # Convert dataclasses/objects to dicts for clean JSON serializability in projected output
        # if the value is list of objects or an object
        if raw_val is not None:
            if hasattr(raw_val, "to_dict"):
                raw_val = raw_val.to_dict()
            elif isinstance(raw_val, list):
                processed_list = []
                for item in raw_val:
                    if hasattr(item, "to_dict"):
                        processed_list.append(item.to_dict())
                    elif hasattr(item, "__dataclass_fields__"):
                        # standard dataclass without to_dict
                        from dataclasses import asdict
                        processed_list.append(asdict(item))
                    else:
                        processed_list.append(item)
                raw_val = processed_list
            elif hasattr(raw_val, "__dataclass_fields__"):
                from dataclasses import asdict
                raw_val = asdict(raw_val)

        # Apply normalization override
        val = apply_normalization(raw_val, f.normalize)
        
        # Determine if value is "missing"
        is_missing = (val is None) or (isinstance(val, list) and len(val) == 0) or (val == "")
        
        # Check required constraint
        if f.required and is_missing:
            raise ValueError(f"Required field '{f.path}' (extracted from '{f.from_path}') is missing for candidate.")
            
        if is_missing:
            if config.on_missing == "error":
                raise ValueError(f"Field '{f.path}' (from '{f.from_path}') is missing, violating 'error' missing policy.")
            elif config.on_missing == "omit":
                continue
            else: # null
                # For list types, return empty list if configured/appropriate, else None
                if f.type_str.endswith("[]"):
                    output[f.path] = []
                else:
                    output[f.path] = None
        else:
            # Validate against config-declared type
            if not type_check(val, f.type_str):
                raise TypeError(f"Value '{val}' for field '{f.path}' does not match expected type '{f.type_str}'.")
            output[f.path] = val

    # Toggle provenance and overall confidence metadata at root level
    if config.include_confidence:
        output["overall_confidence"] = record.overall_confidence
        
    if config.include_provenance:
        # Convert provenance objects to simple dict formats
        from dataclasses import asdict
        output["provenance"] = [asdict(prov) for prov in record.provenance]
        
    return output
