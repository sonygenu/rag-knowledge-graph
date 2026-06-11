"""
Document Loader & Parser using Docling with RapidOCR.

Uses Docling with SimplePipeline and RapidOCR for scanned PDFs.
RapidOCR is Python-only (ONNX-based) — no system packages needed.

Usage:
    python -m src.ingest.loader                    # Parse all files in data/
    python -m src.ingest.loader data/myfile.pdf    # Parse a specific file

Prerequisites (on bastion):
    pip3 install docling rapidocr
"""
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field

from docling.document_converter import DocumentConverter, PdfFormatOption, WordFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
from docling.pipeline.simple_pipeline import SimplePipeline
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend


@dataclass
class ParsedDocument:
    """A parsed document with structured output."""
    source: str
    markdown: str
    metadata: dict = field(default_factory=dict)

    def __repr__(self):
        return f"ParsedDocument(source='{self.source}', chars={len(self.markdown)})"


def create_converter(enable_ocr: bool = True) -> DocumentConverter:
    """
    Create a Docling converter with RapidOCR.
    
    - PDFs: Uses pypdfium2 backend + RapidOCR (Python-only, ONNX-based)
    - DOCX/PPTX/HTML/MD: Uses SimplePipeline (no ML models)
    
    Args:
        enable_ocr: Whether to enable OCR for scanned PDFs (default: True)
    """
    # PDF options with RapidOCR
    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = enable_ocr
    pdf_options.do_table_structure = False  # Skip heavy table model

    if enable_ocr:
        pdf_options.ocr_options = RapidOcrOptions()

    converter = DocumentConverter(
        allowed_formats=[
            InputFormat.PDF,
            InputFormat.DOCX,
            InputFormat.PPTX,
            InputFormat.HTML,
            InputFormat.MD,
        ],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=SimplePipeline,
                backend=PyPdfiumDocumentBackend,
                pipeline_options=pdf_options,
            ),
            InputFormat.DOCX: WordFormatOption(
                pipeline_cls=SimplePipeline,
            ),
        }
    )

    return converter


def parse_document(file_path: str, converter: DocumentConverter = None) -> ParsedDocument:
    """
    Parse a single document using Docling (or plain read for .txt files).
    
    Args:
        file_path: Path to the document file
        converter: Optional pre-created converter (reuse for batch processing)
    
    Returns:
        ParsedDocument with markdown output and metadata
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"  Parsing: {path.name} ...")

    # .txt files: read directly (Docling doesn't support .txt)
    if path.suffix.lower() == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return ParsedDocument(
            source=path.name,
            markdown=content,
            metadata={
                "source": path.name,
                "file_path": str(path.absolute()),
                "file_type": ".txt",
                "size_bytes": path.stat().st_size,
            }
        )

    if converter is None:
        converter = create_converter()

    # Convert the document using Docling
    result = converter.convert(str(path))

    # Export to markdown (preserves structure: headings, tables, lists)
    markdown_output = result.document.export_to_markdown()

    # Collect metadata
    metadata = {
        "source": path.name,
        "file_path": str(path.absolute()),
        "file_type": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
    }

    return ParsedDocument(
        source=path.name,
        markdown=markdown_output,
        metadata=metadata,
    )


def parse_all_documents(directory: str) -> list:
    """
    Parse all supported documents in a directory.
    
    Supported formats: .pdf, .docx, .pptx, .html, .md, .txt
    """
    supported_extensions = {".pdf", ".docx", ".pptx", ".html", ".md", ".txt"}
    documents = []

    dir_path = Path(directory)
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    files = sorted(
        f for f in dir_path.iterdir()
        if f.suffix.lower() in supported_extensions
    )

    if not files:
        print(f"  No supported files found in {directory}")
        print(f"  Supported formats: {', '.join(sorted(supported_extensions))}")
        return documents

    print(f"  Found {len(files)} file(s) to parse\n")

    # Create converter once and reuse for all documents
    converter = create_converter()

    for file_path in files:
        try:
            doc = parse_document(str(file_path), converter=converter)
            documents.append(doc)
            print(f"  ✓ {file_path.name} → {len(doc.markdown)} chars")
        except Exception as e:
            print(f"  ✗ {file_path.name} → Error: {e}")

    return documents


if __name__ == "__main__":
    # Determine data directory
    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")

    if len(sys.argv) > 1:
        # Parse a specific file
        file_path = sys.argv[1]
        doc = parse_document(file_path)
        print(f"\n{'='*60}")
        print(f"Source: {doc.source}")
        print(f"Metadata: {doc.metadata}")
        print(f"{'='*60}")
        print(f"\n--- Markdown Output ---\n")
        print(doc.markdown[:3000])
        if len(doc.markdown) > 3000:
            print(f"\n... ({len(doc.markdown) - 3000} more characters)")
    else:
        # Parse all documents in data/
        print(f"\n📄 Parsing documents from: {os.path.abspath(data_dir)}\n")
        docs = parse_all_documents(data_dir)
        print(f"\n{'='*60}")
        print(f"Total documents parsed: {len(docs)}")
        print(f"{'='*60}")
        for doc in docs:
            print(f"  - {doc}")
