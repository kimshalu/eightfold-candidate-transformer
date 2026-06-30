import os
import json
import csv
from typing import Optional

def detect_source_type(file_path: str) -> Optional[str]:
    """
    Sniffs the input file by extension and a light content check.
    Returns: 'recruiter_csv', 'ats_json', 'resume', 'recruiter_notes', or None if unsupported/unreadable.
    Does not raise exceptions; returns None for unreadable/unsupported files.
    """
    if not os.path.isfile(file_path):
        return None

    filename = os.path.basename(file_path).lower()
    ext = os.path.splitext(filename)[1]

    if ext == '.csv':
        # Light content check for recruiter CSV headers
        try:
            with open(file_path, mode='r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header:
                    header_joined = "".join(header).lower()
                    # Check for recruiter keywords
                    if any(kw in header_joined for kw in ['email', 'phone', 'company', 'title']):
                        return 'recruiter_csv'
        except Exception:
            return None
        return 'recruiter_csv'

    elif ext == '.json':
        # Light content check for ATS JSON
        try:
            with open(file_path, mode='r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
                # Check for single object or list of objects
                first_item = data[0] if isinstance(data, list) and len(data) > 0 else data
                if isinstance(first_item, dict):
                    # ATS JSON specific keys (e.g. ats_id, candidate_name, email_address)
                    if 'ats_id' in first_item or 'candidate_name' in first_item or 'email_address' in first_item:
                        return 'ats_json'
        except Exception:
            return None
        return 'ats_json'

    elif ext in ['.pdf', '.docx']:
        return 'resume'

    elif ext == '.txt':
        # Distinguish between TXT resume and Recruiter Notes
        if 'notes' in filename or 'recruiter' in filename:
            return 'recruiter_notes'
        # Read content to check markers
        try:
            with open(file_path, mode='r', encoding='utf-8', errors='ignore') as f:
                preview = f.read(1000).lower()
                if 'recruiter notes' in preview or 'candidate notes' in preview or 'notes on candidate' in preview:
                    return 'recruiter_notes'
                if any(line.strip().startswith(('Name:', 'Email:', 'Phone:', 'Notes:')) for line in preview.split('\n')[:5]):
                    return 'recruiter_notes'
        except Exception:
            pass
        return 'resume'

    return None
