import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Custom canvas to handle single-page rendering and check height constraints."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        if num_pages > 1:
            print(f"WARNING: Generated PDF has {num_pages} pages, but should be exactly 1 page. Adjust spacing.")
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        self.drawRightString(612 - 36, 20, f"Page {self._pageNumber} of {page_count}")
        self.drawString(36, 20, "Confidential - Eightfold Engineering Intern Assignment")
        self.restoreState()

def build_design_pdf(output_path: str, full_name: str, email: str):
    """Compiles the technical design document into a professional 1-page PDF."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Custom tight styles to fit on one page
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=15,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=2
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#2B6CB0"),
        spaceAfter=8
    )
    
    section_title_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#2D3748"),
        spaceBefore=5,
        spaceAfter=2
    )
    
    body_style = ParagraphStyle(
        'BodyTextTight',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#2D3748"),
        spaceAfter=4
    )
    
    bullet_style = ParagraphStyle(
        'BulletTight',
        parent=body_style,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=2
    )

    story = []

    # Title & Header
    story.append(Paragraph("Multi-Source Candidate Data Transformer — Technical Design", title_style))
    story.append(Paragraph(f"Eightfold Engineering Intern Assignment (Jul–Dec 2026) | {full_name} | {email}", subtitle_style))
    
    # Divider line
    divider = Table([[""]], colWidths=[540], rowHeights=[1.5])
    divider.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#3182CE")),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(divider)
    story.append(Spacer(1, 4))

    # 1. Pipeline Section
    story.append(Paragraph("1. Pipeline Flow", section_title_style))
    story.append(Paragraph(
        "<b>detect</b> &rarr; <b>extract</b> &rarr; <b>normalize</b> &rarr; <b>match/cluster</b> &rarr; <b>merge+confidence</b> &rarr; <b>project</b> &rarr; <b>validate</b> &rarr; <b>emit</b><br/>"
        "&bull; <b>detect</b>: Inspects file headers and extensions to route to source-specific loaders (errors are logged and skipped, never fatal).<br/>"
        "&bull; <b>extract</b>: Parses raw data into standardized fields tagged with metadata (source_id, source_type, method).<br/>"
        "&bull; <b>normalize</b>: Independently normalizes individual fields (phones, dates, countries, skills) to canonical shapes.<br/>"
        "&bull; <b>match/cluster</b>: Groups related records into disjoint candidate-clusters using a <i>Union-Find</i> algorithm.<br/>"
        "&bull; <b>merge+confidence</b>: Resolves conflicts using source-trust and extraction-method weights, scoring field-level confidence.<br/>"
        "&bull; <b>project &amp; validate</b>: Evaluates runtime config paths, executes mapping/normalizations, enforces schema constraints, and emits JSON.",
        body_style
    ))

    # 2. Canonical Schema & Normalized Formats
    story.append(Paragraph("2. Canonical Schema & Normalized Formats", section_title_style))
    story.append(Paragraph(
        "The internal representation of a candidate profile consists of standard structured fields:<br/>"
        "&bull; <b>phones</b>: Standardized to <b>E.164</b> via the <i>phonenumbers</i> library. If missing country codes, falls back to a default region. Ambiguous cases resolve to null with a provenance note (never guessed).<br/>"
        "&bull; <b>dates</b>: Parsed to <b>YYYY-MM</b>. If year-only dates are ingested (e.g. '2020'), they are normalized to '2020-01' with a <i>precision: year</i> provenance flag to avoid presenting fabricated information as fact.<br/>"
        "&bull; <b>country</b>: Normalized to <b>ISO-3166 alpha-2</b> via standard country name and alias lookup tables.<br/>"
        "&bull; <b>skills</b>: Normalized via a canonical dictionary (e.g., 'ReactJS' &rarr; 'react'). Unrecognized skills are lowercased and preserved with lower confidence.",
        body_style
    ))

    # 3. Matching, Merge Policy & Confidence
    story.append(Paragraph("3. Matching, Merge Policy & Confidence", section_title_style))
    story.append(Paragraph(
        "Disjoint candidate records are clustered prior to field merging to prevent cross-contamination:<br/>"
        "&bull; <b>Clustering Keys</b>: Match on normalized emails &rarr; normalized phones &rarr; conservative fuzzy name + current_company. Near-duplicates (same name and company, but differing emails/phones) are explicitly prevented from auto-merging.<br/>"
        "&bull; <b>Confidence Model</b>: Field confidence is defined as <i>source_trust</i> &times; <i>method_confidence</i>. "
        "Source trust values favor objective inputs: <i>recruiter_csv</i> (0.90) and <i>ats_json</i> (0.85) over <i>resume</i> (0.75) and <i>recruiter_notes</i> (0.55). "
        "Method confidence values are: <i>direct_field</i> (1.0), <i>regex_extract</i> (0.8), <i>heuristic_parse</i> (0.6), and <i>derived</i> (0.9).<br/>"
        "&bull; <b>Corroboration &amp; Conflict</b>: Agreement on the same normalized value by multiple independent sources triggers a corroboration boost (+0.05 per source, capped at 1.0). The winning value is emitted, while all losing values are fully retained in the provenance log to prevent silent data loss.",
        body_style
    ))

    # 4. Runtime Output Config
    story.append(Paragraph("4. Runtime Output Config", section_title_style))
    story.append(Paragraph(
        "A separate projection layer consumes the immutable CanonicalRecord through a config JSON to shape output: "
        "it selects field subsets, remaps paths (using dot/bracket notation like <i>emails[0]</i> or <i>skills[].name</i>), "
        "implements local normalization overrides, and toggles provenance and confidence metadata. "
        "The projected result is validated against the config-specified types. Path configurations are validated "
        "against the canonical schema at load time to fail fast rather than failing silently at runtime.",
        body_style
    ))

    # 5. Edge Cases Handled
    story.append(Paragraph("5. Edge Cases Handled", section_title_style))
    story.append(Paragraph(
        "&bull; <b>Near-Duplicates</b>: Candidates with same name and company but different emails remain separate profiles, preventing incorrect identity merge.<br/>"
        "&bull; <b>Stated vs. Computed Experience</b>: Date math over job intervals produces a computed value (method: <i>derived</i>). This wins over stated experience (method: <i>regex_extract</i>) due to its higher method weight, with conflicts preserved.<br/>"
        "&bull; <b>Ambiguous Phone Numbers</b>: Phone numbers lacking country codes that cannot be resolved default to null with an explanatory note.<br/>"
        "&bull; <b>Garbage Resume File</b>: Unreadable files fail closed; the extractor logs the error, contributes zero fields, and other sources proceed.<br/>"
        "&bull; <b>Config Path Typo</b>: Configurations referencing invalid fields are rejected immediately during load time.",
        bullet_style
    ))

    # 6. Deliberately Out of Scope
    story.append(Paragraph("6. Deliberately Out of Scope", section_title_style))
    story.append(Paragraph(
        "&bull; <b>Name-Only Matching</b>: Excluded due to high false-positive risks which could corrupt critical hiring decisions.<br/>"
        "&bull; <b>Live API Integrations</b>: GitHub/LinkedIn APIs are simulated via structured and unstructured input adapters to fit the offline sandbox.<br/>"
        "&bull; <b>User Interface</b>: Focus is kept entirely on core pipeline correctness, regression testing, and the CLI surface.",
        bullet_style
    ))

    # Compile PDF
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Technical Design Document generated successfully at {output_path}")

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Shalu Gupta"
    email = sys.argv[2] if len(sys.argv) > 2 else "shalu.gupta@example.com"
    out = sys.argv[3] if len(sys.argv) > 3 else "ShaluGupta_shalu.gupta@example.com_Eightfold.pdf"
    build_design_pdf(out, name, email)
