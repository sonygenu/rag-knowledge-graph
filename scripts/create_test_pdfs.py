"""
Generate test PDFs for OCR parsing validation.

Creates:
1. A digital PDF (has selectable text — should NOT trigger OCR)
2. A scanned PDF (text as image — SHOULD trigger OCR)

Run on the bastion:
    pip3 install pymupdf pillow
    python3 scripts/create_test_pdfs.py
"""
import fitz  # pymupdf


def create_digital_pdf(output_path: str):
    """Create a digital PDF with selectable text (no OCR needed)."""
    doc = fitz.open()

    # Page 1
    page = doc.new_page()
    text = """QUARTERLY ENGINEERING REPORT - Q2 2026

Team: RAG Ingestion
Manager: Sony Genu
Period: April - June 2026

ACCOMPLISHMENTS:
- Launched Knowledge Graph RAG pipeline (v1.0)
- Reduced document ingestion latency by 35%
- Onboarded 3 new team members
- Achieved 99.9% uptime for Plato Ingestion Service

KEY METRICS:
- Documents processed: 2.4 million
- Average latency: 340ms (down from 520ms)
- Customer satisfaction: 4.7/5.0
- Incidents: 1 (SEV-3, resolved in 47 minutes)
"""
    page.insert_text((72, 72), text, fontsize=11)

    # Page 2
    page2 = doc.new_page()
    text2 = """TEAM MEMBERS AND RESPONSIBILITIES:

Alice Chen - Principal Engineer
  Focus: Pipeline architecture, system design
  Projects: Vector embedding pipeline, Neptune schema

Bob Martinez - Sr. SDE
  Focus: Entity extraction, NLP
  Projects: LLM prompt engineering, batch processing

Carol Zhang - SDE II
  Focus: Graph database, query optimization
  Projects: Neptune loader, Cypher query engine

Dave Wilson - SDE I
  Focus: Document parsing, format support
  Projects: Docling integration, PDF/Excel parsing

DEPENDENCIES:
- Amazon Bedrock (Claude 3 Sonnet) for entity extraction
- Amazon Neptune Serverless for knowledge graph storage
- Amazon OpenSearch for vector embeddings
- Amazon S3 for document storage
"""
    page2.insert_text((72, 72), text2, fontsize=11)

    doc.save(output_path)
    doc.close()
    print(f"✓ Created digital PDF: {output_path} (2 pages, selectable text)")


def create_scanned_pdf(output_path: str):
    """
    Create a simulated scanned PDF (text rendered as image).
    This simulates what a scanner produces — no selectable text layer.
    """
    from PIL import Image, ImageDraw, ImageFont

    pages = []

    # Page 1: Render text as image
    img = Image.new("RGB", (612, 792), "white")  # Letter size at 72 DPI
    draw = ImageDraw.Draw(img)

    lines = [
        "INCIDENT REPORT: INC-2026-0198",
        "",
        "Date: June 8, 2026",
        "Severity: SEV-2",
        "Service: Payment Gateway",
        "Duration: 23 minutes",
        "",
        "SUMMARY:",
        "The payment gateway experienced intermittent",
        "failures between 14:00-14:23 UTC causing",
        "approximately 450 transactions to fail.",
        "",
        "ROOT CAUSE:",
        "Database connection pool exhaustion due to",
        "a slow query introduced in deploy v2.4.1.",
        "",
        "IMPACT:",
        "- 450 failed transactions",
        "- Revenue impact: $67,000",
        "- 12 customer complaints",
        "",
        "RESOLUTION:",
        "Rolled back to v2.4.0. Fix deployed in v2.4.2",
        "with connection pool limits increased.",
    ]

    y_pos = 72
    for line in lines:
        draw.text((72, y_pos), line, fill="black")
        y_pos += 24

    pages.append(img)

    # Page 2
    img2 = Image.new("RGB", (612, 792), "white")
    draw2 = ImageDraw.Draw(img2)

    lines2 = [
        "ACTION ITEMS:",
        "",
        "1. Add connection pool monitoring alarm",
        "   Owner: Bob Martinez",
        "   Due: June 12, 2026",
        "",
        "2. Implement query timeout safeguards",
        "   Owner: Carol Zhang",
        "   Due: June 15, 2026",
        "",
        "3. Add pre-deploy load testing",
        "   Owner: Alice Chen",
        "   Due: June 20, 2026",
        "",
        "ATTENDEES:",
        "- Sony Genu (Sr. Manager)",
        "- Alice Chen (Principal Engineer)",
        "- Bob Martinez (Sr. SDE)",
        "- Platform Team on-call",
    ]

    y_pos = 72
    for line in lines2:
        draw2.text((72, y_pos), line, fill="black")
        y_pos += 24

    pages.append(img2)

    # Save as PDF (images only, no text layer)
    pages[0].save(
        output_path,
        "PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=72.0,
    )
    print(f"✓ Created scanned PDF: {output_path} (2 pages, image-only, needs OCR)")


if __name__ == "__main__":
    create_digital_pdf("data/test-digital.pdf")
    create_scanned_pdf("data/test-scanned.pdf")
    print("\nDone! Test with:")
    print("  python3 -m src.ingest.loader data/test-digital.pdf")
    print("  python3 -m src.ingest.loader data/test-scanned.pdf")
