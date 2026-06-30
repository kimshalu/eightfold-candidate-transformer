import os
import json
import argparse
import logging
from typing import List, Dict, Any, Optional

from eightfold.config import load_config_file, load_config_from_dict
from os import listdir
from os.path import isfile, join

from eightfold.pipeline.detect import detect_source_type
from eightfold.pipeline.extract import extract_from_file
from eightfold.pipeline.cluster import cluster_records
from eightfold.pipeline.merge import merge_cluster
from eightfold.pipeline.project import project_record
from eightfold.models import ProvenanceEntry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("eightfold.cli")

DEFAULT_CONFIG_DICT = {
    "fields": [
        {"path": "candidate_id", "type": "string", "required": True},
        {"path": "full_name", "type": "string", "required": True},
        {"path": "emails", "type": "string[]"},
        {"path": "phones", "type": "string[]"},
        {"path": "location", "type": "object"},
        {"path": "links", "type": "object"},
        {"path": "headline", "type": "string"},
        {"path": "years_experience", "type": "number"},
        {"path": "skills", "type": "object[]"},
        {"path": "experience", "type": "object[]"},
        {"path": "education", "type": "object[]"},
        {"path": "possible_duplicate_of", "type": "string[]"}
    ],
    "include_confidence": True,
    "include_provenance": True,
    "on_missing": "null"
}

def run_pipeline(inputs_dir: str, config_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Runs the entire detection, extraction, normalization, merging, and projection pipeline."""
    # 1. Load config
    if config_path and os.path.exists(config_path):
        logger.info(f"Loading config from: {config_path}")
        config = load_config_file(config_path)
    else:
        logger.info("Using default output configuration.")
        config = load_config_from_dict(DEFAULT_CONFIG_DICT)

    # 2. Scan input directory
    if not os.path.isdir(inputs_dir):
        raise FileNotFoundError(f"Inputs directory not found: {inputs_dir}")

    raw_records = []
    files = [f for f in listdir(inputs_dir) if isfile(join(inputs_dir, f))]

    logger.info(f"Scanning {len(files)} files in {inputs_dir}...")
    for f in files:
        full_path = join(inputs_dir, f)

        source_type = detect_source_type(full_path)
        if not source_type:
            logger.warning(f"Skipping file {f}: Could not detect source format/type.")
            continue

        logger.info(f"Detected file {f} as '{source_type}' format.")

        extracted = extract_from_file(full_path, source_type)
        logger.info(f"Extracted {len(extracted)} raw records from {f}.")
        raw_records.extend(extracted)

    if not raw_records:
        logger.warning("No records extracted from input directory.")
        return []

    # 3. Match / Cluster records using Union-Find
    logger.info(f"Clustering {len(raw_records)} raw records...")
    clusters, possible_duplicates = cluster_records(raw_records)
    logger.info(f"Grouped raw records into {len(clusters)} candidate clusters.")

    # Map each original record (by identity) back to its index in raw_records,
    # since `possible_duplicates` is keyed by index into raw_records.
    id_to_index = {id(r): i for i, r in enumerate(raw_records)}

    # 4. Merge candidates & score confidence
    canonical_records = []
    cluster_index_groups: List[List[int]] = []
    for idx, cluster in enumerate(clusters):
        logger.info(f"Merging cluster {idx + 1} ({len(cluster)} records)...")
        canonical = merge_cluster(cluster)
        canonical_records.append(canonical)
        cluster_index_groups.append([id_to_index[id(r)] for r in cluster])

    # 4b. Attach possible_duplicate_of flags (fuzzy name+company matches that
    # were NOT merged due to a conflicting email/phone — see cluster.py)
    index_to_candidate_id: Dict[int, str] = {}
    for canonical, indices in zip(canonical_records, cluster_index_groups):
        for i in indices:
            index_to_candidate_id[i] = canonical.candidate_id

    flagged_count = 0
    for canonical, indices in zip(canonical_records, cluster_index_groups):
        dup_ids = set()
        for i in indices:
            for j in possible_duplicates.get(i, set()):
                other_id = index_to_candidate_id.get(j)
                if other_id and other_id != canonical.candidate_id:
                    dup_ids.add(other_id)
        canonical.possible_duplicate_of = sorted(dup_ids)
        if dup_ids:
            flagged_count += 1
            canonical.provenance.append(ProvenanceEntry(
                field="possible_duplicate_of",
                source_id=None,
                source_type="system",
                method="fuzzy_name_company_match",
                value=sorted(dup_ids),
                confidence=0.4,
                note="matched_via: fuzzy_name_company"
            ))

    if flagged_count:
        logger.info(f"Flagged {flagged_count} candidate(s) as possible duplicates (same name+company, conflicting email/phone).")

    # 5. Project records using the loaded runtime config
    logger.info(f"Projecting {len(canonical_records)} canonical profiles...")
    projected_outputs = []
    for record in canonical_records:
        try:
            projected = project_record(record, config)
            projected_outputs.append(projected)
        except Exception as e:
            logger.error(f"Failed to project record for candidate {record.full_name}: {e}")
            raise e

    return projected_outputs

def main():
    parser = argparse.ArgumentParser(description="Multi-Source Candidate Data Transformer")
    parser.add_argument("--inputs", required=True, help="Directory containing candidate source files")
    parser.add_argument("--config", required=False, help="Path to runtime config JSON file")
    parser.add_argument("--out", required=False, help="Path to output file for projected JSON")

    args = parser.parse_args()

    try:
        results = run_pipeline(args.inputs, args.config)

        json_output = json.dumps(results, indent=2)
        if args.out:
            out_dir = os.path.dirname(args.out)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(json_output)
            logger.info(f"Successfully wrote output to {args.out}")
        else:
            print(json_output)

    except Exception as e:
        logger.critical(f"Transformer pipeline failed: {e}", exc_info=True)
        exit(1)

if __name__ == "__main__":
    main()