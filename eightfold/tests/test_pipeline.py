import unittest
from datetime import datetime

from eightfold.models import RawRecord, Location, ExperienceEntry, EducationEntry
from eightfold.pipeline.normalize import (
    normalize_phone, normalize_date, normalize_country, normalize_skill
)
from eightfold.pipeline.cluster import cluster_records
from eightfold.pipeline.merge import merge_cluster, compute_experience_years
from eightfold.pipeline.project import project_record, evaluate_path
from eightfold.config import load_config_from_dict

class TestNormalizers(unittest.TestCase):
    def test_phone_normalization(self):
        # Valid US number
        val, note = normalize_phone("+1 (650) 555-0100")
        self.assertEqual(val, "+16505550100")
        self.assertIsNone(note)
        
        # Valid number without country code (falls back to default region US)
        val, note = normalize_phone("650 555 0100", default_region="US")
        self.assertEqual(val, "+16505550100")
        self.assertIsNone(note)
        
        # Ambiguous / Short number
        val, note = normalize_phone("12345")
        self.assertIsNone(val)
        self.assertEqual(note, "normalize_failed: ambiguous_region")

    def test_date_normalization(self):
        # YYYY-MM
        val, note = normalize_date("2020-05")
        self.assertEqual(val, "2020-05")
        self.assertIsNone(note)
        
        # Year-only
        val, note = normalize_date("2020")
        self.assertEqual(val, "2020-01")
        self.assertEqual(note, "precision: year")
        
        # Textual month
        val, note = normalize_date("May 2020")
        self.assertEqual(val, "2020-05")
        self.assertIsNone(note)
        
        # Textual month with different casing
        val, note = normalize_date("2020 DEC")
        self.assertEqual(val, "2020-12")
        self.assertIsNone(note)

    def test_country_normalization(self):
        val, note = normalize_country("United States")
        self.assertEqual(val, "US")
        self.assertIsNone(note)
        
        val, note = normalize_country("usa")
        self.assertEqual(val, "US")
        self.assertIsNone(note)
        
        val, note = normalize_country("invalid country name")
        self.assertIsNone(val)
        self.assertEqual(note, "normalize_failed: unknown_country")

    def test_skill_normalization(self):
        self.assertEqual(normalize_skill("ReactJS"), "react")
        self.assertEqual(normalize_skill("React.js"), "react")
        self.assertEqual(normalize_skill("python3"), "python")
        self.assertEqual(normalize_skill("UnrecognizedSkill"), "unrecognizedskill")


class TestClustering(unittest.TestCase):
    def test_clustering_rules(self):
        # Candidate A: records overlap via email
        r1 = RawRecord(source_id="s1", source_type="recruiter_csv", method="direct_field",
                       full_name="Alice Smith", emails=["alice@example.com"])
        r2 = RawRecord(source_id="s2", source_type="ats_json", method="direct_field",
                       full_name="Alice Smith", emails=["alice@example.com"], phones=["+16505550100"])
                       
        # Candidate B: near-duplicate (same name+company, but different emails)
        # We need to construct experience so that they share current company
        exp_c1 = [ExperienceEntry(company="Apple", title="PM", start="2018-01", end="")]
        r3 = RawRecord(source_id="s3", source_type="recruiter_csv", method="direct_field",
                       full_name="Charlie Brown", emails=["charlie1@example.com"], experience=exp_c1)
        r4 = RawRecord(source_id="s4", source_type="ats_json", method="direct_field",
                       full_name="Charlie Brown", emails=["charlie2@example.com"], experience=exp_c1)
                       
        clusters, possible_duplicates= cluster_records([r1, r2, r3, r4])
        self.assertEqual(len(clusters), 3)  # [r1, r2], [r3], [r4] (r3 and r4 must not auto-merge)


class TestMergingAndConfidence(unittest.TestCase):
    def test_merge_conflict_and_confidence(self):
        # Alice Smith has different titles across Recruiter CSV (trust 0.90, direct_field 1.0 -> 0.90)
        # and Recruiter Notes (trust 0.55, heuristic 0.6 -> 0.33)
        r1 = RawRecord(
            source_id="csv_row",
            source_type="recruiter_csv",
            method="direct_field",
            full_name="Alice Smith",
            emails=["alice@example.com"],
            experience=[ExperienceEntry(company="Google", title="Senior Frontend Engineer")]
        )
        r2 = RawRecord(
            source_id="notes_txt",
            source_type="recruiter_notes",
            method="heuristic_parse",
            full_name="Alice Smith",
            emails=["alice@example.com"],
            experience=[ExperienceEntry(company="Google", title="Tech Lead")]
        )
        
        canonical = merge_cluster([r1, r2])
        
        # Verify winner title
        # The CSV title is direct_field (conf: 0.9 * 1.0 = 0.9)
        # The Notes title is heuristic (conf: 0.55 * 0.6 = 0.33)
        # Experience list should have Senior Frontend Engineer
        self.assertEqual(canonical.experience[0].title, "Senior Frontend Engineer")
        
        # Verify both values are preserved in provenance
        prov_titles = [p.value["title"] for p in canonical.provenance if p.field == "experience"]
        self.assertIn("Senior Frontend Engineer", prov_titles)
        self.assertIn("Tech Lead", prov_titles)

    def test_experience_computation(self):
        # Test stated vs. computed experience winning policy
        # Resume has stated experience "8 years" (regex_extract -> trust 0.75 * method 0.8 = 0.6)
        # Resume also has work history from 2018-05 to 2024-05 (6 years) (derived -> trust 0.75 * method 0.9 = 0.675)
        # The computed value (6 years) should win since derived (0.675) > regex_extract (0.6)
        r = RawRecord(
            source_id="resume_pdf",
            source_type="resume",
            method="regex_extract",
            full_name="Bob Miller",
            years_experience=8.0,
            experience=[ExperienceEntry(company="Meta", title="Engineer", start="2018-05", end="2024-05")]
        )
        
        canonical = merge_cluster([r])
        
        # Winner should be around 6.0 years
        self.assertAlmostEqual(canonical.years_experience, 6.0, delta=0.1)
        
        # Both values should be in provenance
        prov_years = [p.value for p in canonical.provenance if p.field == "years_experience"]
        # One of them is 8.0, one is 6.0
        self.assertIn(8.0, prov_years)
        self.assertTrue(any(isinstance(v, float) and abs(v - 6.0) < 0.1 for v in prov_years))


class TestProjection(unittest.TestCase):
    def test_custom_projection(self):
        # Build a CanonicalRecord manually
        cand = merge_cluster([
            RawRecord(
                source_id="test_s",
                source_type="recruiter_csv",
                method="direct_field",
                full_name="John Doe",
                emails=["john@example.com"],
                phones=["+1 650 555 0100"],
                skills=["ReactJS", "Python"]
            )
        ])
        
        config_dict = {
            "fields": [
                { "path": "name", "from": "full_name", "type": "string" },
                { "path": "email", "from": "emails[0]", "type": "string" },
                { "path": "primary_phone", "from": "phones[0]", "type": "string", "normalize": "E164" },
                { "path": "skill_list", "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
            ],
            "include_confidence": True,
            "include_provenance": False,
            "on_missing": "null"
        }
        
        config = load_config_from_dict(config_dict)
        projected = project_record(cand, config)
        
        self.assertEqual(projected["name"], "John Doe")
        self.assertEqual(projected["email"], "john@example.com")
        self.assertEqual(projected["primary_phone"], "+16505550100")
        self.assertEqual(projected["skill_list"], ["react", "python"])
        self.assertIn("overall_confidence", projected)
        self.assertNotIn("provenance", projected)  # Toggled off by default in config unless include_provenance=True

if __name__ == "__main__":
    unittest.main()
