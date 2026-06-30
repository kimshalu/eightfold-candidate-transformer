import os
import shutil
import tempfile
import unittest
from typing import Dict, Any

from eightfold.utils.mock_generator import generate_mock_inputs
from eightfold.cli import run_pipeline

class TestRegressionGoldProfile(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for inputs
        self.test_dir = tempfile.mkdtemp()
        generate_mock_inputs(self.test_dir)

    def tearDown(self):
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def test_pipeline_regression(self):
        # Run pipeline with default config
        results = run_pipeline(self.test_dir, None)
        
        # Verify candidate counts
        # Alice Smith (merged from 4 sources)
        # Bob Johnson (ambiguous phone, from CSV)
        # Charlie Brown 1 (from CSV, near dup 1)
        # Charlie Brown 2 (from JSON, near dup 2)
        # David Miller (garbage resume, from Notes)
        # Total expected candidates = 5
        self.assertEqual(len(results), 5, f"Expected 5 candidates, got {len(results)}")
        
        # Index results by name for testing
        candidates_by_name: Dict[str, Dict[str, Any]] = {}
        for cand in results:
            name = cand.get("full_name")
            if name:
                # Store multiple candidates with the same name if they occur (near duplicates)
                candidates_by_name.setdefault(name, []).append(cand)

        # 1. Verify Alice Smith (Conflict Candidate)
        self.assertIn("Alice Smith", candidates_by_name)
        alice_list = candidates_by_name["Alice Smith"]
        self.assertEqual(len(alice_list), 1, "Alice Smith should be merged into a single profile")
        alice = alice_list[0]
        
        # Winning title should be "Senior Frontend Engineer" from Recruiter CSV (trust 0.9, direct_field 1.0)
        # over "Staff Software Engineer" (ATS, trust 0.85) or "Tech Lead" (Notes, trust 0.55)
        # or "Software Engineer III" (Resume, trust 0.75, regex 0.8 -> 0.6)
        self.assertTrue(len(alice["experience"]) > 0, "Alice should have experience entries")
        
        # CSV title is current role, let's verify which title won.
        # Since CSV current company Google title is "Senior Frontend Engineer", let's check.
        # Wait, the recruiter CSV has experience mapping where we add company=Google, title="Senior Frontend Engineer".
        # Let's check experience entries to see which one won.
        winning_exp = alice["experience"][0]
        self.assertEqual(winning_exp["title"], "Senior Frontend Engineer", 
                         f"Expected 'Senior Frontend Engineer' to win, got '{winning_exp['title']}'")
        
        # Check that all conflict values are preserved in provenance
        provenance_entries = alice.get("provenance", [])
        self.assertTrue(len(provenance_entries) > 0, "Provenance should be populated")
        
        experience_provenance = [p for p in provenance_entries if p["field"] == "experience"]
        self.assertTrue(len(experience_provenance) >= 4, "Should have at least 4 experience provenance items")
        
        prov_titles = []
        for p in experience_provenance:
            val = p.get("value")
            if isinstance(val, dict) and "title" in val:
                prov_titles.append(val["title"])
                
        self.assertIn("Senior Frontend Engineer", prov_titles)
        self.assertIn("Staff Software Engineer", prov_titles)
        self.assertIn("Software Engineer III", prov_titles)
        self.assertIn("Tech Lead", prov_titles)

        # 2. Verify David Miller (Garbage Resume Candidate)
        self.assertIn("David Miller", candidates_by_name)
        david_list = candidates_by_name["David Miller"]
        self.assertEqual(len(david_list), 1, "David Miller profile should be created despite garbage resume")
        david = david_list[0]
        
        # Verify his details came from notes (Netflix, Engineering Manager)
        self.assertEqual(david["emails"], ["david.miller@example.com"])
        self.assertEqual(david["phones"], ["+14155550199"]) # Normalized Netflix notes phone
        self.assertTrue(len(david["experience"]) > 0)
        self.assertEqual(david["experience"][0]["company"], "Netflix")
        self.assertEqual(david["experience"][0]["title"], "Engineering Manager")

        # 3. Verify Bob Johnson (Ambiguous Phone Candidate)
        self.assertIn("Bob Johnson", candidates_by_name)
        bob = candidates_by_name["Bob Johnson"][0]
        # Phone should fail to E.164 normalization, falling back to empty list [] (since it's a list type in default config)
        self.assertEqual(bob["phones"], [], f"Ambiguous phone should be empty list, got {bob['phones']}")
        
        # Provenance should show the normalization failure note for Bob's phone
        bob_phone_prov = [p for p in bob.get("provenance", []) if p["field"] == "phones"]
        self.assertTrue(len(bob_phone_prov) > 0, "Bob phone provenance should be recorded")
        self.assertEqual(bob_phone_prov[0]["note"], "normalize_failed: ambiguous_region")

        # 4. Verify Charlie Brown (Near Duplicate Candidates)
        self.assertIn("Charlie Brown", candidates_by_name)
        charlie_list = candidates_by_name["Charlie Brown"]
        self.assertEqual(len(charlie_list), 2, "Near-duplicates Charlie Brown should NOT be merged")

if __name__ == "__main__":
    unittest.main()
