"""
Document Loader & Parser using Docling.

Docling converts PDF, DOCX, PPTX, HTML, and Markdown into structured
representations preserving layout, tables, headings, and reading order.

Usage:
    python -m src.ingest.loader                    # Parse all files in data/
    python -m src.ingest.loader data/myfile.pdf    # Parse a specific file
"""
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from docling.document_converter import DocumentConverter


@dataclass
class ParsedDocument:
    """A parsed document with structured output."""
    source: str
    markdown: str
    metadata: dict = field(default_factory=dict)

    def __repr__(self):
        return f"ParsedDocument(source='{self.source}', chars={len(self.markdown)})"


def parse_document(file_path: str) -> ParsedDocument:
    """
    Parse a single document using Docling.
    
    Docling handles: PDF, DOCX, PPTX, HTML, Markdown, Images
    It preserves structure: headings, tables, reading order, metadata.
    
    Args:
        file_path: Path to the document file
    
    Returns:
        ParsedDocument with markdown output and metadata
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"  Parsing: {path.name} ...")

    # Create converter and process the document
    converter = DocumentConverter()
    result = converter.convert(str(path))

    # Export to markdown (preserves structure)
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

    for file_path in files:
        try:
            doc = parse_document(str(file_path))
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
