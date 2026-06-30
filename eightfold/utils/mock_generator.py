import os
import csv
import json
import logging
from reportlab.pdfgen import canvas

logger = logging.getLogger("eightfold.mock_generator")

def generate_pdf(file_path: str, text_lines: list):
    """Generates a simple, valid PDF file containing text_lines using reportlab."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        c = canvas.Canvas(file_path)
        y = 800
        for line in text_lines:
            c.drawString(50, y, line)
            y -= 20
        c.save()
        logger.info(f"Generated PDF: {file_path}")
    except Exception as e:
        logger.error(f"Failed to generate PDF {file_path}: {e}")

def generate_mock_inputs(output_dir: str):
    """Generates mock input files representing different candidate scenarios."""
    os.makedirs(output_dir, exist_ok=True)

    # 1. Recruiter CSV export
    csv_path = os.path.join(output_dir, "recruiter_export.csv")
    with open(csv_path, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["name", "email", "phone", "current_company", "title", "years_experience"])
        # Alice Smith (Conflict Candidate)
        writer.writerow(["Alice Smith", "alice.smith@example.com", "+1 650 555 0100", "Google", "Senior Frontend Engineer", "6"])
        # Bob Johnson (Ambiguous Phone)
        writer.writerow(["Bob Johnson", "bob.johnson@example.com", "12345", "Meta", "Software Engineer", "4"])
        # Charlie Brown (Near duplicate 1)
        writer.writerow(["Charlie Brown", "charlie.b1@example.com", "+1 650 555 0101", "Apple", "Product Manager", "5"])

    # 2. ATS JSON export
    ats_data = [
        {
            "ats_id": "ats_alice",
            "candidate_name": "Alice Smith",
            "email_address": "alice.smith@example.com",
            "telephone": "+1-650-555-0100",
            "company_name": "Google",
            "job_title": "Staff Software Engineer",
            "location": {
                "city": "Mountain View",
                "region": "CA",
                "country": "United States"
            },
            "skills": ["React", "TypeScript", "Python"],
            "years_experience": 7.0,
            "experience": [
                {
                    "company": "Google",
                    "title": "Staff Software Engineer",
                    "start": "2020-01",
                    "end": ""
                }
            ],
            "education": [
                {
                    "institution": "Stanford University",
                    "degree": "B.S.",
                    "field": "Computer Science",
                    "end_year": "2018"
                }
            ]
        },
        {
            "ats_id": "ats_charlie2",
            "candidate_name": "Charlie Brown",
            "email_address": "charlie.b2@example.com",
            "telephone": "+1-650-555-9999",
            "company_name": "Apple",
            "job_title": "Product Manager",
            "location": {
                "city": "Cupertino",
                "region": "CA",
                "country": "US"
            },
            "skills": ["Product Strategy", "Agile"],
            "years_experience": 5.0
        }
    ]
    json_path = os.path.join(output_dir, "ats_export.json")
    with open(json_path, mode='w', encoding='utf-8') as f:
        json.dump(ats_data, f, indent=2)

    # 3. Alice Smith (Conflict Candidate) - Resume PDF
    alice_resume_path = os.path.join(output_dir, "alice_resume.pdf")
    alice_lines = [
        "Alice Smith",
        "Email: alice.smith@example.com",
        "Phone: +1 650 555 0100",
        "Experience:",
        "Software Engineer III at Google (2018-05 to 2020-01)",
        "Summary: Developed highly interactive UI features",
        "Skills: ReactJS, JavaScript, CSS, HTML",
        "Education: BS CS from Stanford (2018)"
    ]
    generate_pdf(alice_resume_path, alice_lines)

    # 4. Alice Smith (Conflict Candidate) - Recruiter Notes TXT
    alice_notes_path = os.path.join(output_dir, "alice_notes.txt")
    with open(alice_notes_path, mode='w', encoding='utf-8') as f:
        f.write(
            "Recruiter Notes on Candidate Alice Smith\n"
            "Email: alice.smith@example.com\n"
            "Phone: +1 (650) 555-0100\n"
            "Company: Google\n"
            "Title: Tech Lead\n"
            "Skills: Python, Django, React, Go\n"
            "Experience: 8 years\n"
        )

    # 5. Candidate 2 (Garbage File Candidate): David Miller
    # David Miller - Garbage Resume PDF
    garbage_resume_path = os.path.join(output_dir, "david_miller_resume.pdf")
    with open(garbage_resume_path, mode='wb') as f:
        f.write(b"%PDF-1.4\n% THIS IS CORRUPT GARBAGE PDF DATA THAT CANNOT BE PARSED BY PYPDF\n%%EOF")

    # David Miller - Recruiter Notes TXT (Saves the day!)
    david_notes_path = os.path.join(output_dir, "david_miller_notes.txt")
    with open(david_notes_path, mode='w', encoding='utf-8') as f:
        f.write(
            "Notes on David Miller\n"
            "Email: david.miller@example.com\n"
            "Phone: +1 415 555 0199\n"
            "Company: Netflix\n"
            "Title: Engineering Manager\n"
            "Skills: Java, Spring Boot, AWS, Kubernetes\n"
            "Experience: 10 years\n"
        )

if __name__ == "__main__":
    import sys
    generate_mock_inputs(sys.argv[1] if len(sys.argv) > 1 else "mock_inputs")
