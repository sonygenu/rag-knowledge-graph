"""
Document Loader & Parser using Docling with RapidOCR.

Uses Docling with SimplePipeline and RapidOCR for scanned PDFs.
RapidOCR is Python-only (ONNX-based) — no system packages needed.

Includes file type validation using magic bytes (first 261 bytes only).

Usage:
    python -m src.ingest.loader                    # Parse all files in data/
    python -m src.ingest.loader data/myfile.pdf    # Parse a specific file

Prerequisites (on bastion):
    pip3 install docling rapidocr
"""
import os
import sys
import logging
from pathlib import Path
from dataclasses import dataclass, field

import filetype
from docling.document_converter import DocumentConverter, PdfFormatOption, WordFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
from docling.pipeline.simple_pipeline import SimplePipeline
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- File Type Validation ---

# Binary formats detected via magic bytes
SUPPORTED_BINARY_MIMES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}

# Text formats detected via file extension (no magic bytes for these)
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm", ".csv"}

# All supported extensions (for directory scanning)
ALL_SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".md", ".txt", ".markdown", ".csv"
}


class UnsupportedFormatError(Exception):
    """Raised when a document format is not supported (4xx equivalent)."""
    pass


def detect_file_type(file_path: str) -> str:
    """
    Detect document type using magic bytes + extension fallback.
    
    Only reads the first 261 bytes of the file — safe for any file size.
    
    Args:
        file_path: Path to the file
    
    Returns:
        Normalized file extension (e.g., ".pdf", ".docx", ".md")
    
    Raises:
        UnsupportedFormatError: If file type is not supported (4xx to customer)
    """
    path = Path(file_path)
    
    # Step 1: Try magic bytes (reads only first 261 bytes)
    kind = filetype.guess(file_path)
    
    if kind is not None:
        logger.info(
            f"Magic bytes detected: mime={kind.mime}, "
            f"extension={kind.extension}, file={path.name}"
        )
        
        if kind.mime in SUPPORTED_BINARY_MIMES:
            detected_type = SUPPORTED_BINARY_MIMES[kind.mime]
            logger.info(f"✓ Validated binary format: {detected_type} for {path.name}")
            return detected_type
        else:
            logger.warning(
                f"✗ Unsupported binary format: mime={kind.mime}, "
                f"extension={kind.extension}, file={path.name}"
            )
            raise UnsupportedFormatError(
                f"Unsupported file format: {kind.mime} ({kind.extension}). "
                f"Supported binary formats: PDF, DOCX, PPTX, XLSX"
            )
    
    # Step 2: No magic bytes found — likely a text file, check extension
    ext = path.suffix.lower()
    logger.info(
        f"No magic bytes found (text file). "
        f"Falling back to extension: '{ext}' for {path.name}"
    )
    
    if ext in SUPPORTED_TEXT_EXTENSIONS:
        logger.info(f"✓ Validated text format: {ext} for {path.name}")
        return ext
    
    # Step 3: Unknown format — reject
    logger.warning(f"✗ Unsupported format: extension='{ext}', file={path.name}")
    raise UnsupportedFormatError(
        f"Cannot determine file type for: {path.name}. "
        f"Extension '{ext}' is not supported. "
        f"Supported formats: PDF, DOCX, PPTX, XLSX, HTML, Markdown, TXT, CSV"
    )


# --- Document Parsing ---

@dataclass
class ParsedDocument:
    """A parsed document with structured output."""
    source: str
    markdown: str
    detected_type: str
    metadata: dict = field(default_factory=dict)

    def __repr__(self):
        return (
            f"ParsedDocument(source='{self.source}', "
            f"type='{self.detected_type}', chars={len(self.markdown)})"
        )


def create_converter(enable_ocr: bool = True) -> DocumentConverter:
    """
    Create a Docling converter with RapidOCR.
    """
    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = enable_ocr
    pdf_options.do_table_structure = False

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
    Validate file type and parse document.
    
    1. Validates file type using magic bytes (first 261 bytes only)
    2. Rejects unsupported formats with UnsupportedFormatError (4xx)
    3. Parses supported documents using Docling, openpyxl, or plain read
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Step 1: Validate file type (reads only 261 bytes)
    detected_type = detect_file_type(file_path)
    logger.info(f"Processing {path.name} as {detected_type}")

    # Step 2: Parse based on detected type
    if detected_type == ".txt":
        # Plain text — read directly
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"Read {len(content)} chars from text file {path.name}")
        return ParsedDocument(
            source=path.name,
            markdown=content,
            detected_type=detected_type,
            metadata={
                "source": path.name,
                "file_path": str(path.absolute()),
                "file_type": detected_type,
                "size_bytes": path.stat().st_size,
            }
        )

    if detected_type == ".csv":
        # CSV — read as plain text (structured already)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"Read {len(content)} chars from CSV file {path.name}")
        return ParsedDocument(
            source=path.name,
            markdown=content,
            detected_type=detected_type,
            metadata={
                "source": path.name,
                "file_path": str(path.absolute()),
                "file_type": detected_type,
                "size_bytes": path.stat().st_size,
            }
        )

    if detected_type == ".xlsx":
        # Excel — parse with openpyxl in read_only mode (memory-safe)
        return parse_excel_file(file_path, detected_type)

    # All other supported formats — use Docling
    if converter is None:
        converter = create_converter()

    result = converter.convert(str(path))
    markdown_output = result.document.export_to_markdown()

    logger.info(f"Docling parsed {path.name} → {len(markdown_output)} chars")

    return ParsedDocument(
        source=path.name,
        markdown=markdown_output,
        detected_type=detected_type,
        metadata={
            "source": path.name,
            "file_path": str(path.absolute()),
            "file_type": detected_type,
            "size_bytes": path.stat().st_size,
        }
    )


def parse_excel_file(file_path: str, detected_type: str) -> ParsedDocument:
    """
    Parse an Excel file using openpyxl in read_only mode.
    
    Converts each sheet to a markdown table.
    Uses read_only=True for memory safety (streams rows, doesn't load full file).
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ImportError(
            "openpyxl is required for Excel parsing. Install with: pip3 install openpyxl"
        )

    path = Path(file_path)
    logger.info(f"Parsing Excel file: {path.name} (read_only mode)")

    # read_only=True: streams rows, safe for large files
    wb = load_workbook(str(path), read_only=True, data_only=True)

    markdown_parts = []
    total_rows = 0
    sheet_count = 0

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        sheet_count += 1
        logger.info(f"  Processing sheet: '{sheet_name}'")

        rows = []
        for row in sheet.iter_rows(values_only=True):
            # Convert None values to empty strings
            rows.append([str(cell) if cell is not None else "" for cell in row])

        if not rows:
            logger.info(f"  Sheet '{sheet_name}' is empty, skipping")
            continue

        # Build markdown table
        headers = rows[0]
        markdown_parts.append(f"## Sheet: {sheet_name}\n")

        # Header row
        markdown_parts.append("| " + " | ".join(headers) + " |")
        # Separator
        markdown_parts.append("| " + " | ".join(["---"] * len(headers)) + " |")
        # Data rows
        for row in rows[1:]:
            # Pad row if shorter than headers
            padded = row + [""] * (len(headers) - len(row))
            markdown_parts.append("| " + " | ".join(padded[:len(headers)]) + " |")
            total_rows += 1

        markdown_parts.append("")  # Empty line between sheets

    wb.close()

    markdown_output = "\n".join(markdown_parts)
    logger.info(
        f"Excel parsed: {sheet_count} sheet(s), "
        f"{total_rows} data rows, {len(markdown_output)} chars"
    )

    return ParsedDocument(
        source=path.name,
        markdown=markdown_output,
        detected_type=detected_type,
        metadata={
            "source": path.name,
            "file_path": str(path.absolute()),
            "file_type": detected_type,
            "size_bytes": path.stat().st_size,
            "num_sheets": sheet_count,
            "num_rows": total_rows,
        }
    )


def parse_all_documents(directory: str) -> list:
    """Parse all supported documents in a directory."""
    documents = []

    dir_path = Path(directory)
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    files = sorted(f for f in dir_path.iterdir() if f.is_file())

    if not files:
        logger.warning(f"No files found in {directory}")
        return documents

    logger.info(f"Found {len(files)} file(s) in {directory}")

    converter = create_converter()

    for file_path in files:
        try:
            doc = parse_document(str(file_path), converter=converter)
            documents.append(doc)
            print(f"  ✓ {file_path.name} → {doc.detected_type} → {len(doc.markdown)} chars")
        except UnsupportedFormatError as e:
            print(f"  ✗ {file_path.name} → REJECTED: {e}")
        except Exception as e:
            print(f"  ✗ {file_path.name} → ERROR: {e}")

    return documents


if __name__ == "__main__":
    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        try:
            doc = parse_document(file_path)
            print(f"\n{'='*60}")
            print(f"Source: {doc.source}")
            print(f"Detected Type: {doc.detected_type}")
            print(f"Metadata: {doc.metadata}")
            print(f"{'='*60}")
            print(f"\n--- Parsed Output ---\n")
            print(doc.markdown[:3000])
            if len(doc.markdown) > 3000:
                print(f"\n... ({len(doc.markdown) - 3000} more characters)")
        except UnsupportedFormatError as e:
            print(f"\n❌ REJECTED (400): {e}")
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
    else:
        print(f"\n📄 Parsing documents from: {os.path.abspath(data_dir)}\n")
        docs = parse_all_documents(data_dir)
        print(f"\n{'='*60}")
        print(f"Total documents parsed: {len(docs)}")
        print(f"{'='*60}")
        for doc in docs:
            print(f"  - {doc}")
