"""
Hybrid Format-Aware Chunker.

Detects content structure (headers, tables, paragraphs) and applies
the best splitting strategy for each. Pure Python — no extra libraries.

Usage:
    python -m src.ingest.chunker                           # Chunk all docs in data/
    python -m src.ingest.chunker data/sample-team-wiki.md  # Chunk a specific file
"""
import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A chunk of content with metadata for traceability."""
    content: str
    metadata: dict = field(default_factory=dict)

    def __repr__(self):
        section = self.metadata.get("section", "?")
        content_type = self.metadata.get("content_type", "?")
        return (
            f"Chunk(section='{section}', type={content_type}, "
            f"chars={len(self.content)})"
        )


def detect_content_type(text: str) -> str:
    """
    Detect whether text is primarily tabular, has headers, or is plain text.
    
    Returns: "structured" (has headers), "tabular" (markdown tables), or "plain"
    """
    lines = text.strip().split("\n")
    
    header_count = sum(1 for line in lines if re.match(r'^#{1,6}\s', line))
    table_count = sum(1 for line in lines if line.strip().startswith("|"))
    
    if table_count > len(lines) * 0.5:
        return "tabular"
    elif header_count > 0:
        return "structured"
    else:
        return "plain"


def chunk_by_headers(text: str, source: str, max_size: int = 1500, min_size: int = 100) -> list:
    """
    Split markdown by headers (##, ###, etc.)
    
    - Each section becomes a chunk
    - Sections too large → split further by paragraphs
    - Sections too small → merge with the next section
    """
    # Split on markdown headers, keeping the header in the result
    parts = re.split(r'(^#{1,4}\s+.+$)', text, flags=re.MULTILINE)
    
    sections = []
    current_header = ""
    current_content = ""
    
    for part in parts:
        if re.match(r'^#{1,4}\s+', part):
            # This is a header — save previous section if exists
            if current_content.strip():
                sections.append((current_header, current_content.strip()))
            current_header = part.strip()
            current_content = ""
        else:
            current_content += part
    
    # Don't forget the last section
    if current_content.strip():
        sections.append((current_header, current_content.strip()))
    
    # Build chunks with merging and splitting logic
    chunks = []
    chunk_index = 0
    
    for header, content in sections:
        full_section = f"{header}\n\n{content}" if header else content
        
        if len(full_section) <= max_size:
            # Section fits in one chunk
            chunks.append(Chunk(
                content=full_section,
                metadata={
                    "source": source,
                    "section": header.lstrip("#").strip() if header else "Introduction",
                    "chunk_index": chunk_index,
                    "content_type": "narrative",
                    "char_count": len(full_section),
                }
            ))
            chunk_index += 1
        else:
            # Section too large — split by paragraphs
            sub_chunks = chunk_by_paragraphs(
                full_section, source, max_size,
                section_name=header.lstrip("#").strip() if header else "Introduction",
                start_index=chunk_index,
            )
            chunks.extend(sub_chunks)
            chunk_index += len(sub_chunks)
    
    # Merge tiny chunks (< min_size) with their neighbor
    chunks = merge_small_chunks(chunks, min_size)
    
    return chunks


def chunk_by_paragraphs(text: str, source: str, max_size: int = 1500,
                        section_name: str = "", start_index: int = 0) -> list:
    """
    Split text by paragraphs (double newline), accumulating until max_size.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""
    chunk_index = start_index
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # Would adding this paragraph exceed the limit?
        if len(current_chunk) + len(para) + 2 > max_size and current_chunk:
            chunks.append(Chunk(
                content=current_chunk.strip(),
                metadata={
                    "source": source,
                    "section": section_name,
                    "chunk_index": chunk_index,
                    "content_type": "narrative",
                    "char_count": len(current_chunk.strip()),
                }
            ))
            chunk_index += 1
            current_chunk = ""
        
        current_chunk += para + "\n\n"
    
    # Last chunk
    if current_chunk.strip():
        chunks.append(Chunk(
            content=current_chunk.strip(),
            metadata={
                "source": source,
                "section": section_name,
                "chunk_index": chunk_index,
                "content_type": "narrative",
                "char_count": len(current_chunk.strip()),
            }
        ))
    
    return chunks


def chunk_table(text: str, source: str, rows_per_chunk: int = 30) -> list:
    """
    Split markdown tables into chunks of N rows.
    Always includes column headers in each chunk.
    """
    lines = text.strip().split("\n")
    chunks = []
    chunk_index = 0
    
    # Find all table blocks (header row + separator + data rows)
    current_section = ""
    table_header = ""
    table_separator = ""
    data_rows = []
    non_table_buffer = ""
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check if this is a section header
        if re.match(r'^#{1,4}\s+', line):
            # Flush any pending table
            if data_rows:
                chunks.extend(_emit_table_chunks(
                    table_header, table_separator, data_rows,
                    source, current_section, chunk_index, rows_per_chunk
                ))
                chunk_index += len(chunks)
                data_rows = []
            current_section = line.lstrip("#").strip()
            i += 1
            continue
        
        # Detect table header (line with | that's followed by a separator |---|)
        if "|" in line and i + 1 < len(lines) and re.match(r'\|[\s\-:|]+\|', lines[i + 1]):
            # Flush previous table if any
            if data_rows:
                chunks.extend(_emit_table_chunks(
                    table_header, table_separator, data_rows,
                    source, current_section, chunk_index, rows_per_chunk
                ))
                chunk_index = len(chunks)
                data_rows = []
            
            table_header = line
            table_separator = lines[i + 1]
            i += 2
            continue
        
        # If we're inside a table (have header), collect data rows
        if table_header and line.strip().startswith("|"):
            data_rows.append(line)
        else:
            # Non-table content — add to buffer
            if non_table_buffer or line.strip():
                non_table_buffer += line + "\n"
        
        i += 1
    
    # Flush remaining table
    if data_rows:
        chunks.extend(_emit_table_chunks(
            table_header, table_separator, data_rows,
            source, current_section, chunk_index, rows_per_chunk
        ))
    
    # If there was non-table content, chunk it by paragraphs
    if non_table_buffer.strip():
        para_chunks = chunk_by_paragraphs(non_table_buffer.strip(), source)
        chunks.extend(para_chunks)
    
    return chunks


def _emit_table_chunks(header, separator, rows, source, section, start_index, rows_per_chunk):
    """Helper to split table rows into chunks, each with headers."""
    chunks = []
    chunk_index = start_index
    
    for i in range(0, len(rows), rows_per_chunk):
        batch = rows[i:i + rows_per_chunk]
        content = "\n".join([header, separator] + batch)
        chunks.append(Chunk(
            content=content,
            metadata={
                "source": source,
                "section": section,
                "chunk_index": chunk_index,
                "content_type": "table",
                "char_count": len(content),
                "row_range": f"{i+1}-{i+len(batch)}",
            }
        ))
        chunk_index += 1
    
    return chunks


def merge_small_chunks(chunks: list, min_size: int = 100) -> list:
    """Merge chunks smaller than min_size with their next neighbor."""
    if not chunks:
        return chunks
    
    merged = []
    i = 0
    while i < len(chunks):
        if len(chunks[i].content) < min_size and i + 1 < len(chunks):
            # Merge with next chunk
            combined_content = chunks[i].content + "\n\n" + chunks[i + 1].content
            merged.append(Chunk(
                content=combined_content,
                metadata={
                    **chunks[i + 1].metadata,
                    "char_count": len(combined_content),
                    "merged": True,
                }
            ))
            i += 2
        else:
            merged.append(chunks[i])
            i += 1
    
    return merged


def chunk_document(parsed_doc, max_size: int = 1500, rows_per_chunk: int = 30) -> list:
    """
    Chunk a ParsedDocument using the hybrid strategy.
    
    Detects content type and applies the best chunking approach:
    - Scanned PDF (OCR'd) → page-based chunking
    - Structured (has headers) → section-based
    - Tabular (markdown tables) → row-group based
    - Plain text → paragraph-based
    """
    text = parsed_doc.markdown
    source = parsed_doc.source
    
    # Special handling for scanned PDFs (OCR output is flat text, page-separated)
    is_scanned_pdf = parsed_doc.metadata.get("pdf_type") == "scanned"
    is_hybrid_pdf = parsed_doc.metadata.get("pdf_type") == "hybrid"
    
    if is_scanned_pdf or is_hybrid_pdf:
        logger.info(f"Using page-based chunking for scanned/hybrid PDF: {source}")
        chunks = chunk_by_pages(text, source, max_size=max_size)
        logger.info(f"Chunked {source} → {len(chunks)} chunks (page-based)")
        return chunks
    
    # Standard detection for non-scanned documents
    content_type = detect_content_type(text)
    logger.info(f"Detected content type: '{content_type}' for {source}")
    
    if content_type == "tabular":
        chunks = chunk_table(text, source, rows_per_chunk=rows_per_chunk)
    elif content_type == "structured":
        chunks = chunk_by_headers(text, source, max_size=max_size)
    else:
        chunks = chunk_by_paragraphs(text, source, max_size=max_size)
    
    logger.info(f"Chunked {source} → {len(chunks)} chunks")
    return chunks


def chunk_by_pages(text: str, source: str, max_size: int = 1500) -> list:
    """
    Chunk OCR'd text by page boundaries.
    
    Scanned PDFs parsed by Docling typically have page breaks as sections.
    If pages are too large, split further by paragraphs.
    If pages are too small, merge with the next page.
    
    Falls back to paragraph-based if no page structure is detected.
    """
    # Docling separates pages with markdown headers or page markers
    # Try splitting on common page separators
    page_patterns = [
        r'\n---\s*\n',           # Horizontal rules between pages
        r'\n#{1,2}\s+Page\s+\d+',  # "## Page 1" style markers
    ]
    
    pages = None
    for pattern in page_patterns:
        parts = re.split(pattern, text)
        if len(parts) > 1:
            pages = parts
            break
    
    # If no page markers found, split by large paragraph gaps
    if pages is None or len(pages) <= 1:
        # Fall back: split by double blank lines (paragraph groups)
        pages = re.split(r'\n{3,}', text)
    
    # If still just one big chunk, use paragraph-based splitting
    if len(pages) <= 1:
        logger.info(f"No page structure found in {source}, falling back to paragraph chunking")
        return chunk_by_paragraphs(text, source, max_size=max_size)
    
    chunks = []
    chunk_index = 0
    current_chunk = ""
    current_page_start = 1
    
    for page_num, page_text in enumerate(pages, 1):
        page_text = page_text.strip()
        if not page_text:
            continue
        
        # Would adding this page exceed max_size?
        if len(current_chunk) + len(page_text) + 2 > max_size and current_chunk:
            # Emit current chunk
            chunks.append(Chunk(
                content=current_chunk.strip(),
                metadata={
                    "source": source,
                    "section": f"Pages {current_page_start}-{page_num - 1}",
                    "chunk_index": chunk_index,
                    "content_type": "ocr_text",
                    "char_count": len(current_chunk.strip()),
                    "page_range": f"{current_page_start}-{page_num - 1}",
                }
            ))
            chunk_index += 1
            current_chunk = ""
            current_page_start = page_num
        
        current_chunk += page_text + "\n\n"
    
    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(Chunk(
            content=current_chunk.strip(),
            metadata={
                "source": source,
                "section": f"Pages {current_page_start}-{len(pages)}",
                "chunk_index": chunk_index,
                "content_type": "ocr_text",
                "char_count": len(current_chunk.strip()),
                "page_range": f"{current_page_start}-{len(pages)}",
            }
        ))
    
    # If no chunks were created (all empty), fall back
    if not chunks:
        return chunk_by_paragraphs(text, source, max_size=max_size)
    
    return chunks


# --- CLI ---

if __name__ == "__main__":
    import os
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Import the loader
    from src.ingest.loader import parse_document, parse_all_documents
    
    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
    
    if len(sys.argv) > 1:
        # Chunk a specific file
        file_path = sys.argv[1]
        doc = parse_document(file_path)
        chunks = chunk_document(doc)
        
        print(f"\n{'='*60}")
        print(f"Source: {doc.source}")
        print(f"Detected Type: {doc.detected_type}")
        print(f"Total Chunks: {len(chunks)}")
        print(f"{'='*60}")
        
        for i, chunk in enumerate(chunks):
            print(f"\n--- Chunk {i} ({chunk.metadata.get('content_type')}, "
                  f"{chunk.metadata.get('char_count')} chars) ---")
            print(f"Section: {chunk.metadata.get('section', 'N/A')}")
            print(f"Content:\n{chunk.content[:500]}")
            if len(chunk.content) > 500:
                print(f"... ({len(chunk.content) - 500} more chars)")
    else:
        # Chunk all docs in data/
        print(f"\n📄 Chunking documents from: {os.path.abspath(data_dir)}\n")
        docs = parse_all_documents(data_dir)
        
        print(f"\n{'='*60}")
        for doc in docs:
            chunks = chunk_document(doc)
            print(f"\n{doc.source} → {len(chunks)} chunks:")
            for chunk in chunks:
                print(f"  [{chunk.metadata.get('content_type')}] "
                      f"section='{chunk.metadata.get('section', '')}' "
                      f"chars={chunk.metadata.get('char_count')}")
        print(f"{'='*60}")
