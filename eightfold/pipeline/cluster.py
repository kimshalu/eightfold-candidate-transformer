from typing import List, Dict, Set, Tuple, Optional
from eightfold.models import RawRecord
import re

class UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))
        self.rank = [1] * size

    def find(self, i: int) -> int:
        if self.parent[i] == i:
            return i
        self.parent[i] = self.find(self.parent[i])  # Path compression
        return self.parent[i]

    def union(self, i: int, j: int) -> bool:
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            if self.rank[root_i] > self.rank[root_j]:
                self.parent[root_j] = root_i
            elif self.rank[root_i] < self.rank[root_j]:
                self.parent[root_i] = root_j
            else:
                self.parent[root_j] = root_i
                self.rank[root_i] += 1
            return True
        return False


def clean_string(s: Optional[str]) -> str:
    """Helper to lowercase, strip punctuation and whitespace."""
    if not s:
        return ""
    # Strip company suffixes for conservative matching
    s = re.sub(r'\b(inc|corp|co|ltd|llc|limited|corporation)\b', '', s.lower())
    return re.sub(r'[^a-z0-9]', '', s)


def get_current_company(r: RawRecord) -> Optional[str]:
    """Best-effort extraction of the candidate's current company from experience entries."""
    if r.experience:
        for exp in r.experience:
            if not exp.end or exp.end.lower() in ["present", "current", ""]:
                return exp.company
        return r.experience[0].company
    return None


def cluster_records(
    records: List[RawRecord], default_region: str = "US"
) -> Tuple[List[List[RawRecord]], Dict[int, Set[int]]]:
    """
    Groups records into clusters representing the same person using Union-Find.

    Match priority:
    1. Exact normalized email match
    2. Exact normalized phone match
    3. Conservative fuzzy name + current_company match (only if email/phone do not conflict) -> MERGED
    4. Same name + current_company but CONFLICTING email/phone -> NOT merged, flagged as possible_duplicates

    Returns:
        clusters: list of record-groups representing the same person (to be merged downstream)
        possible_duplicates: dict mapping a record's index (in `records`) to the set of
            other record indices it was matched to by name+company but NOT merged with,
            due to a conflicting email or phone. Caller should translate these indices into
            final candidate_ids after clustering/merging and surface them as
            `possible_duplicate_of` on the resulting canonical records.
    """
    n = len(records)
    uf = UnionFind(n)

    # Precompute cleaned representations for matching
    cleaned_emails: List[Set[str]] = []
    cleaned_phones: List[Set[str]] = []
    name_company_keys: List[Optional[Tuple[str, str]]] = []

    for r in records:
        emails = {e.strip().lower() for e in r.emails if e and e.strip()}
        cleaned_emails.append(emails)

        phones = {p.strip() for p in r.phones if p and p.strip()}
        cleaned_phones.append(phones)

    # Compute name_company_keys
    for r in records:
        c_name = clean_string(r.full_name)
        comp = get_current_company(r)
        c_comp = clean_string(comp)
        if c_name and c_comp:
            name_company_keys.append((c_name, c_comp))
        else:
            name_company_keys.append(None)

    # 1. Union by exact email match
    email_to_indices: Dict[str, List[int]] = {}
    for i, emails in enumerate(cleaned_emails):
        for email in emails:
            email_to_indices.setdefault(email, []).append(i)
    for email, indices in email_to_indices.items():
        for idx in indices[1:]:
            uf.union(indices[0], idx)

    # 2. Union by exact phone match
    phone_to_indices: Dict[str, List[int]] = {}
    for i, phones in enumerate(cleaned_phones):
        for phone in phones:
            if "normalize_failed" not in phone:
                phone_to_indices.setdefault(phone, []).append(i)
    for phone, indices in phone_to_indices.items():
        for idx in indices[1:]:
            uf.union(indices[0], idx)

    # 3 & 4. Union (or flag) by name + current_company with conflict guard
    possible_duplicates: Dict[int, Set[int]] = {}

    name_comp_to_indices: Dict[Tuple[str, str], List[int]] = {}
    for i, key in enumerate(name_company_keys):
        if key:
            name_comp_to_indices.setdefault(key, []).append(i)

    for key, indices in name_comp_to_indices.items():
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                idx_a = indices[i]
                idx_b = indices[j]

                emails_a = cleaned_emails[idx_a]
                emails_b = cleaned_emails[idx_b]
                has_email_conflict = bool(emails_a and emails_b and not (emails_a & emails_b))

                phones_a = {p for p in cleaned_phones[idx_a] if "normalize_failed" not in p}
                phones_b = {p for p in cleaned_phones[idx_b] if "normalize_failed" not in p}
                has_phone_conflict = bool(phones_a and phones_b and not (phones_a & phones_b))

                if not has_email_conflict and not has_phone_conflict:
                    # No conflicting identity signal -> safe to merge
                    uf.union(idx_a, idx_b)
                elif has_email_conflict or has_phone_conflict:
                    # Same name+company, but a contact field actively conflicts ->
                    # flag as a possible duplicate instead of merging
                    possible_duplicates.setdefault(idx_a, set()).add(idx_b)
                    possible_duplicates.setdefault(idx_b, set()).add(idx_a)

    # Group records into clusters
    clusters: Dict[int, List[RawRecord]] = {}
    for i in range(n):
        root = uf.find(i)
        clusters.setdefault(root, []).append(records[i])

    return list(clusters.values()), possible_duplicates