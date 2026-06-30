# Multi-Source Candidate Data Transformer

A Python pipeline that ingests, cleans, clusters, and merges candidate profiles from multiple structured and unstructured sources (Recruiter CSV, ATS JSON, PDF Resumes, Recruiter Notes) into a single, high-trust Canonical profile with detailed provenance tracking and confidence scoring.

### Requirements
- **Python 3.10+**
- Packages pinned in `requirements.txt` (`phonenumbers`, `pypdf`, `python-docx`).
- `reportlab` (optional, required only for running the PDF design compiler tool).

---

## Features

- **Format Sniffing (Detect)**: Automatically determines file format by extension and content-preview.
- **Resilient Extraction**: Extracts data via structured loaders and regex/heuristic parsers (e.g. extracts PDF text using `pypdf`, DOCX using `python-docx`). Corrupted or unreadable files fail closed without crashing the pipeline.
- **Normalization Engine**:
  - Phones normalized to **E.164** using the `phonenumbers` library. Falls back to a default region. Ambiguous phones become `null` with a provenance warning (`normalize_failed: ambiguous_region`).
  - Dates normalized to **YYYY-MM**. Year-only dates (e.g., "2020") become "2020-01" with a `precision: year` provenance note.
  - Countries normalized to **ISO-3166 alpha-2** via a lookup map.
  - Skills normalized using a canonical alias translation dictionary (e.g. `ReactJS` / `React.js` -> `react`).
- **Union-Find Clustering**: Groups records using emails and phones, with a conservative name + company fallback. Employs a strict email/phone conflict guard to prevent merging near-duplicates.
- **Possible-Duplicate Flagging**: Candidates that share an exact name + current company but have *conflicting* emails/phones are **not** auto-merged. Instead they're kept as separate records and cross-referenced via a `possible_duplicate_of` field (plus a provenance entry, `method: fuzzy_name_company_match`), so the ambiguity is surfaced to a human reviewer rather than silently resolved either way. See `mock_inputs/recruiter_export.csv` (the two "Charlie Brown" / Apple rows) for a worked example in `output/out_default.json`.
- **Trust-Weighted Merge & Confidence**: Combines fields using a weighted scoring model (`source_trust * method_confidence`). Agreeing independent sources trigger a corroboration boost (`+0.05` per source).
- **No Data Loss**: Emits the highest confidence value, but fully preserves all losing candidate values in the `provenance` metadata.
- **Config-Driven Projection**: Projects canonical internal records onto any schema at runtime (supports nested dot/bracket selectors like `emails[0]` or `skills[].name`, custom type validation, normalization overrides, metadata toggles, and missing value policies: `null`, `omit`, or `error`). It validates config paths at load-time to fail-fast.

---

## Out of Scope (Descoped Items)

1. **GitHub / LinkedIn Live API Integration**: Descoped due to API key management and Terms of Service constraints. Structured JSON/CSV and unstructured notes/PDF inputs serve as proxy sources (one structured + one unstructured, per the assignment's minimum requirement).
2. **Aggressive Fuzzy Name-Only Matching**: Only a conservative name + current_company fallback is implemented, and only as a *non-merging* flag (`possible_duplicate_of`), never an automatic merge — to eliminate the risk of silently conflating two different people, which the assignment explicitly calls out as a hiring-decision risk.
3. **Advanced Graphical User Interface**: Descoped to focus efforts on core merging correctness, configuration robustness, and the command-line surface, per the assignment's own stated priorities.

---

## Project Structure

```
eightfold/              # pipeline package (detect, extract, normalize, cluster, merge, project, cli)
configs/                # default.json, custom_config.json
mock_inputs/             # generated mock candidate source files
output/                  # produced pipeline output (committed for review)
  ├── out_default.json
  └── out_custom.json
tools/                   # pdf_generator.py — compiles the Step 1 design doc (not part of the pipeline package)
eightfold/tests/         # unit + regression tests
requirements.txt
```

---

## Running the Application

### 1. Installation
Install pipeline dependencies from the requirements file:
```bash
pip install -r requirements.txt
```
To generate the design document PDF, also install `reportlab`:
```bash
pip install reportlab
```

### 2. Generate Mock Inputs
Generates mock candidates representing all edge cases (multi-source conflicts, a corrupted/unreadable resume, an ambiguous phone number, and a same-name+company "possible duplicate" pair) into a directory:
```bash
python -m eightfold.utils.mock_generator mock_inputs
```

### 3. Run Pipeline via CLI
Run the transformer with the default canonical schema projection, writing output into `output/`:
```bash
python -m eightfold.cli --inputs mock_inputs --out outputs/out_default.json
```

Or run the pipeline using the custom configuration matching the assignment's example config (`primary_email`, E.164 `phone`, flattened canonical `skills`, no provenance):
```bash
python -m eightfold.cli --inputs mock_inputs --config configs/custom_config.json --out outputs/out_custom.json
```


---

## Running Tests

Execute the unit tests, including the clustering/duplicate-flagging and gold-profile regression tests:
```bash
python -m unittest discover -s eightfold/tests
```

To run a single test verbosely :
```bash
python -m unittest eightfold.tests.test_pipeline.TestClustering.test_clustering_rules -v
```

---

## Technical Design Document Tool

A professional one-page technical design summary has been generated in PDF format at the workspace root:
- **Design PDF**: `Shalu Kumari_shalujha6044@gmail.com_Eightfold.pdf`
- **PDF Compiler Script**: `tools/pdf_generator.py` (standalone — not imported by the pipeline package)
- **Compile Command**:
  ```bash
  python tools/pdf_generator.py "Shalu Kumari" "shalujha6044@gmail.com" "Shalu Kumari_shalujha6044@gmail.com_Eightfold.pdf"
  ```

---

## Sample JSON Outputs

### 1. Custom Profile (Filtered & Remapped Schema)
From `output/out_custom.json`:
```json
[
  {
    "full_name": "Alice Smith",
    "primary_email": "alice.smith@example.com",
    "phone": "+16505550100",
    "skills": [
      "python",
      "django",
      "react",
      "go",
      "javascript",
      "typescript"
    ],
    "overall_confidence": 0.816
  }
]
```

### 2. Conflict Provenance (Default Schema Slice)
From `output/out_default.json`:
```json
{
  "full_name": "Alice Smith",
  "emails": ["alice.smith@example.com"],
  "phones": ["+16505550100"],
  "experience": [
    {
      "company": "Google",
      "title": "Senior Frontend Engineer"
    }
  ],
  "provenance": [
    {
      "field": "experience.title",
      "source_id": "recruiter_export.csv_row_0",
      "source_type": "recruiter_csv",
      "method": "direct_field",
      "value": "Senior Frontend Engineer",
      "confidence": 0.9
    },
    {
      "field": "experience.title",
      "source_id": "alice_notes.txt",
      "source_type": "recruiter_notes",
      "method": "heuristic_parse",
      "value": "Tech Lead",
      "confidence": 0.358
    }
  ]
}
```
`Senior Frontend Engineer` wins the title slot due to its higher confidence (CSV `direct_field` = `0.90`) versus the recruiter notes (`heuristic_parse` ≈ `0.358`), while the conflicting `Tech Lead` value is fully preserved in provenance rather than discarded.

### 3. Possible-Duplicate Flag (Default Schema Slice)
From `output/out_default.json` — two "Charlie Brown" / Apple / Product Manager records with different emails, kept separate and cross-flagged:
```json
{
  "candidate_id": "cand_fba1de2564a9",
  "full_name": "Charlie Brown",
  "emails": ["charlie.b2@example.com"],
  "possible_duplicate_of": ["cand_042c7769b9db"]
}
```
```json
{
  "candidate_id": "cand_042c7769b9db",
  "full_name": "Charlie Brown",
  "emails": ["charlie.b1@example.com"],
  "possible_duplicate_of": ["cand_fba1de2564a9"]
}
```
