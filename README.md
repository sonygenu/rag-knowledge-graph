# RAG Knowledge Graph

A Retrieval-Augmented Generation system powered by Neo4j knowledge graphs for accurate, context-rich AI responses.

---

## What Is a Knowledge Graph?

A knowledge graph is a database that stores information in **Nodes** and **Relationships**.

Both nodes and relationships can have **properties** — key-value pairs that add detail and context to the data.

Nodes can be given **labels** to group them together — for example, `:Person`, `:Course`, `:Service`.

Relationships always have a **type** and a **direction** — e.g., `(Sony) -[TEACHES]-> (Course)`.

It represents information as a network of **nodes** (entities) connected by **edges** (relationships). Unlike tables or documents, a knowledge graph captures not just *what* things are, but *how they relate to each other*.

### The Building Blocks

| Concept | What it is | Example |
|---------|-----------|---------|
| **Node** | An entity — a person, place, thing, or concept | `(Sony)`, `(Mishka)`, `(Course)` |
| **Edge** | A relationship between two nodes | `[KNOWS]`, `[TEACHES]`, `[INTRODUCES]` |
| **Property** | Metadata on a node or edge | `since: 2015`, `name: "Sony"` |
| **Label** | A category/type for a node | `:Person`, `:Course` |

### A Simple Example

Let's say Sony and Mishka are friends, Sony teaches a course, and Mishka introduces students to that same course:

```
┌───────┐                        ┌─────────┐
│ Sony  │ ──[KNOWS since 2015]──▶│ Mishka  │
│:Person│                        │:Person  │
└───┬───┘                        └────┬────┘
    │                                 │
    │ [TEACHES]              [INTRODUCES]
    │                                 │
    ▼                                 ▼
    ┌─────────────────────────────────┐
    │            Course               │
    │           :Course               │
    └─────────────────────────────────┘
```

Reading this graph, we instantly know:

- **Sony** is a Person who **knows** Mishka (since 2015)
- **Sony teaches** a Course
- **Mishka introduces** the same Course
- Sony and Mishka are connected through both a personal relationship *and* a shared course

### Why This Matters

In a traditional database, you'd need multiple tables and JOINs to answer: *"Who does Sony know that also works on the same course?"*

In a knowledge graph, it's a single traversal:

```
(Sony) -[KNOWS]-> (Mishka) -[INTRODUCES]-> (Course) <-[TEACHES]- (Sony)
```

The graph reveals that Sony and Mishka are not just friends — they collaborate on the same course from different roles. This kind of structural insight is invisible to flat text or tabular data.

### From Simple Graphs to RAG

Now imagine this scaled to thousands of entities — people, services, documents, teams, APIs — all connected by typed relationships. When a user asks a question, the knowledge graph lets your RAG system:

1. **Identify** the entities mentioned in the query
2. **Traverse** their connections to find related context
3. **Return** structured, connected facts instead of just similar-sounding text

This is the foundation everything else in this project builds on.

---

## Why Knowledge Graphs Matter for RAG

### The Problem with Vanilla RAG

Standard RAG works like this: chunk documents → embed them → retrieve top-k by vector similarity → feed to LLM. It works well for "find me relevant passages" 

## Knowledge Graph RAG — Real-World Examples

### 1. Relationships Between Entities

**Query:** "What marketing campaigns is Sarah managing that use the email automation platform?"

- **Pure vector RAG** retrieves documents mentioning Sarah or email automation — but can't connect them
- **KG traverses:** `Sarah → owns → Campaigns → depends_on → EmailPlatform`
- **Returns:** "Sarah manages 3 active campaigns (Spring Launch, Q3 Nurture, Re-engagement) all routed through the email platform"

### 2. Multi-hop Reasoning

**Query:** "Who is responsible for the data source that powers our sales dashboard?"

- **Pure vector RAG:** returns docs about dashboards or data sources — probably misses the ownership chain
- **KG traverses:** `SalesDashboard → reads_from → CRMExport → owned_by → RevOpsTeam → contact → jane@company.com`
- 3 hops, zero ambiguity — impossible with similarity search alone

### 3. Structured Facts

**Query:** "Who is the primary contact for the payments system this weekend?"

- **Pure vector RAG:** retrieves old runbooks, past incident docs — stale and unstructured
- **KG holds:** `PaymentsSystem → oncall_rotation → {weekOf: Jun 9} → Person: Marcus → phone: ...`
- Returns a precise, live structured fact — not a paragraph to parse

### 4. Disambiguation

**Query:** "Tell me about Falcon — the programming language or the fighter jet?"

- **Pure vector RAG:** mixes results from both meanings based on nearest embeddings — confusing
- **KG maintains distinct nodes:** `Falcon (Entity: Aircraft, F-16)` vs `Falcon (Entity: ProgrammingLanguage, OpenSource)`
- User context (e.g. they work in aerospace) tips the KG to resolve to the right entity before retrieval even starts

---

> **The pattern across all four:** Vector search finds what's *nearby*. Knowledge graphs know what's *connected*, what's *current*, and what something actually *is*. Together, they make RAG answers feel less like "here are some relevant paragraphs" and more like "here is the answer."

### What Knowledge Graphs Add

| Capability | Vector RAG | KG-enhanced RAG |
|-----------|:----------:|:---------------:|
| Semantic similarity | ✅ | ✅ |
| Entity relationships | ❌ | ✅ |
| Multi-hop reasoning | ❌ | ✅ |
| Structured facts | ❌ | ✅ |
| Disambiguation | ❌ | ✅ |
| Explainability | ❌ | ✅ |

### How It Works Together

A knowledge graph stores information as **entities** (nodes) and **relationships** (edges), preserving the structure and connections that exist in your data:

```
[Document] --mentions--> [Entity: Service A]
[Entity: Service A] --owned_by--> [Entity: Payments Team]
[Entity: Payments Team] --reports_to--> [Entity: VP Engineering]
```

This project combines both approaches:

```
User Query
    ├── Vector Search → semantically similar text chunks
    └── Graph Query  → structurally connected entities and relationships
                 ↓
        Combined Context → LLM → Grounded Answer
```

Vector search handles fuzzy, semantic similarity. The knowledge graph handles precise, structural reasoning. Together, they eliminate the blind spots each has alone.

> **Bottom line:** Vector RAG is great at *finding*. Knowledge graphs make RAG great at *understanding*. Combined, they're the backbone of truly intelligent enterprise AI.

---

## Document Ingestion Pipeline

This is the first component we're building — validating each step locally end-to-end before moving forward.

```
Load Docs → Parse → Chunk → Extract Entities → Resolve & Dedup → Load to Neo4j
```

### Step 1: Document Loading & Parsing

- Accept documents (PDF, DOCX, HTML, Markdown)
- Use **Docling** or PyMuPDF to extract clean text
- Preserve document structure (headings, sections, tables)
- Output: raw text + metadata (source, page, section)

### Step 2: Chunking

- Split documents into meaningful segments (by section, paragraph, or semantic boundary)
- Maintain metadata per chunk: source file, page number, section heading
- Configurable chunk size and overlap

### Step 3: Entity & Relationship Extraction

- Use LLM (AWS Bedrock Claude) to extract structured entities and relationships from each chunk
- Prompt with a defined schema: extract people, services, teams, concepts
- Output as structured JSON: `{entities: [...], relationships: [...]}`

### Step 4: Entity Resolution & Deduplication

- Normalize entity names ("AWS Lambda", "Lambda", "lambda function" → single node)
- Merge duplicate entities across chunks
- Assign canonical IDs

### Step 5: Load into Neo4j

- Create nodes with labels and properties
- Create relationships with types and properties
- Create vector embeddings on nodes/chunks for hybrid search

### Step 6: Index & Validate

- Create indexes for fast lookup (full-text, vector, composite)
- Validate graph connectivity
- Log stats (nodes created, relationships formed, duplicates merged)

---

### Project Structure

```
rag-knowledge-graph/
├── src/
│   ├── ingest/                # Step 1 & 2: Document loading, parsing, chunking
│   │   ├── loader.py          # Accept and load documents
│   │   ├── parser.py          # Extract text with structure preserved
│   │   └── chunker.py         # Split into meaningful segments
│   ├── extract/               # Step 3: LLM-powered extraction
│   │   ├── entity_extractor.py
│   │   └── prompts.py         # Extraction prompts and output schemas
│   ├── resolve/               # Step 4: Entity resolution
│   │   └── resolver.py        # Normalize, dedup, assign IDs
│   ├── graph/                 # Step 5 & 6: Neo4j operations
│   │   ├── neo4j_client.py    # Connection management
│   │   ├── schema.py          # Node labels, relationship types, constraints
│   │   └── loader.py          # Create nodes and relationships
│   └── config/
│       └── settings.py        # Neo4j, LLM, and chunking configuration
├── data/                      # Sample documents for testing
├── tests/
├── docker-compose.yml         # Local Neo4j instance
├── requirements.txt
├── .env.example
└── README.md
```

### Infrastructure Setup (Neptune Serverless)

Neptune runs in your AWS VPC. To set it up:

1. **Create a Neptune Serverless cluster** in the AWS Console
   - Go to Neptune → Create database → Serverless
   - Choose a VPC and subnets
   - Set min/max NCUs (start with 1/2.5 for dev)

2. **Connect from your laptop** (Neptune is VPC-only):
   - Option A: SSH tunnel through a bastion/EC2 in the same VPC
   - Option B: Use AWS Cloud9 in the same VPC
   - Option C: Use a VPN connection to the VPC

3. **Update `.env`** with your Neptune endpoint:
   ```
   NEPTUNE_ENDPOINT=your-cluster.cluster-xxxxx.us-west-2.neptune.amazonaws.com
   NEPTUNE_PORT=8182
   ```

4. **Verify connection:**
   ```bash
   curl -X POST https://$NEPTUNE_ENDPOINT:8182/openCypher \
     --data-urlencode "query=RETURN 1"
   ```

---

## Architecture (Full System — Planned)

```
┌─────────────────────────────────────────────────────┐
│                  Document Ingestion                   │
│  Parse → Extract Entities → Resolve → Load to Graph  │
└─────────────────────┬───────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│                 Neo4j Knowledge Graph                 │
│  Nodes: Entities    Edges: Relationships             │
│  + Vector Index on node/chunk embeddings             │
└─────────────────────┬───────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│                   Query Engine                        │
│  NL → Cypher generation + Vector similarity search   │
└─────────────────────┬───────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│                    RAG Chain                          │
│  Graph context + Vector context → LLM → Response     │
└─────────────────────────────────────────────────────┘
```

---

## Tech Stack

- **Graph Database:** Amazon Neptune Serverless (openCypher)
- **LLM:** AWS Bedrock (Claude)
- **Entity Extraction:** LLM-powered with structured output
- **Vector Search:** Neptune vector similarity (or OpenSearch)
- **Framework:** LangChain / LlamaIndex
- **Language:** Python
- **Infrastructure:** AWS (Neptune, Bedrock, VPC)

---

## Project Status

🚧 **In Progress** — building incrementally. This README will be updated as components are added.

| Component | Status | Details |
|-----------|--------|---------|
| Project setup | ✅ Complete | Repo, structure, infra (Neptune, bastion, IAM) |
| Document ingestion pipeline | 🔧 In Progress | See breakdown below |
| Entity/relationship extraction | ⬜ Not started | LLM-powered (Bedrock Claude) |
| Neo4j graph schema & loading | ⬜ Not started | Write to Neptune |
| Query engine (NL → Cypher) | ⬜ Not started | Natural language to openCypher |
| Hybrid retrieval (graph + vector) | ⬜ Not started | Graph + vector combined |
| RAG chain with LLM | ⬜ Not started | End-to-end Q&A |
| Evaluation & benchmarks | ⬜ Not started | Accuracy, latency |

### Document Ingestion Pipeline — Detailed Status

| Sub-component | Status | Details |
|---------------|--------|---------|
| File type detection (magic bytes) | ✅ Complete | Validates format using first 261 bytes, rejects unsupported types with 4xx |
| Document parsing (Docling + RapidOCR) | ✅ Complete | Supports PDF, DOCX, PPTX, HTML, Markdown, TXT |
| Excel parsing (openpyxl) | ✅ Complete | Streaming read_only mode, converts sheets to markdown tables |
| PDF OCR (scanned documents) | ✅ Complete | Smart detection (digital vs scanned), RapidOCR for image-based PDFs |
| Multi-format testing | ✅ Complete | Tested with .md, .txt, .html, .xlsx, digital PDF, scanned PDF on bastion |
| Chunking | ✅ Complete | Hybrid format-aware: section-based, table row-group, paragraph-based, page-based (OCR) |
| S3 integration | ⬜ Not started | Load documents from S3 buckets instead of local filesystem |
| Batch processing | ⬜ Not started | Process large document sets concurrently |

---

## File Type Detection: How Magic Bytes Work

### What Are Magic Bytes?

Magic bytes are a hidden **file format identifier** embedded at the very start of every binary file. They're invisible to users — you never see them when opening a document. They exist for computers to identify the file format regardless of the file extension.

If you open a PDF in a raw hex editor, you'd see:

```
Byte position:  0    1    2    3    4    5    6    ...
Hex values:     25   50   44   46   2D   31   2E  ...
As text:        %    P    D    F    -    1    .   ...
```

The first 4 bytes spell `%PDF` — that's the magic bytes.

### Magic Bytes by File Type

| File type | First raw bytes | Readable | What creates it |
|-----------|----------------|----------|-----------------|
| PDF | `25 50 44 46` | `%PDF` | Adobe, any PDF writer |
| ZIP/DOCX/XLSX | `50 4B 03 04` | `PK..` | Microsoft Office (these are ZIP archives internally) |
| PNG image | `89 50 4E 47` | `.PNG` | Any image editor |
| JPEG image | `FF D8 FF` | `ÿØÿ` | Cameras, image editors |

### Why Text Files Don't Have Magic Bytes

Text files (`.txt`, `.md`, `.html`) are just raw text from byte 0. There's no stamp — the file starts immediately with your content:

```
Text file:   H  e  l  l  o     w  o  r  l  d
PDF file:    %  P  D  F  -  1  .  7  [then actual content...]
```

That's why for text files we fall back to checking the file extension.

### How We Use It (261 Bytes Only)

Our code reads **only the first 261 bytes** of any file — safe for any file size (even 1 GB):

```python
filetype.guess("report.pdf")
# Reads bytes 0-260 → sees "%PDF" → returns mime="application/pdf"

filetype.guess("notes.md")
# Reads bytes 0-260 → no known signature → returns None (fall back to extension)
```

### Scanned vs Digital PDFs

Magic bytes **cannot** distinguish between digital and scanned PDFs — both start with `%PDF`. To detect scanned PDFs, we extract text from the first few pages:

```
File → Magic bytes → "It's a PDF"
                         ↓
              Extract text from first 3 pages
                         ↓
            ┌────────────┴────────────┐
            ↓                         ↓
   Has text (>50 chars/page)    No text (<50 chars/page)
            ↓                         ↓
    Digital PDF → skip OCR     Scanned PDF → run OCR
```

---

## Chunking Strategy

### Why Chunk?

LLMs have context limits and perform better on focused text. Chunking gives us:

- **Better entity extraction** — LLM focuses on one topic at a time
- **Lower cost** — smaller inputs = fewer tokens
- **Traceability** — know exactly which section an entity came from
- **Vector search readiness** — embeddings work best on focused passages

### Approach: Hybrid Format-Aware Chunking

Since all document types are parsed into markdown, the chunker detects the content structure and applies the best splitting strategy:

```
ParsedDocument (markdown)
    │
    ├── Has headers (##, ###)?
    │       YES → Section-based chunking
    │       Split by headers, merge small sections, split large ones
    │
    ├── Is tabular (| ... |)?
    │       YES → Row-group chunking
    │       Keep headers + N rows per chunk
    │
    └── Plain text, no structure?
            → Paragraph-based chunking
            Split on \n\n, accumulate until size limit
```

### Strategy by Source Format

| Source Format | Chunking Approach | Why |
|--------------|-------------------|-----|
| Markdown/HTML | Section-based (split by headers) | Headings = natural topic boundaries |
| TXT | Paragraph-based with size cap | No headers, but paragraphs are meaningful |
| Excel/CSV | Sheet + row-group based | Each sheet is a topic; rows are entities |
| PDF | Section-based (Docling preserves headers) | Parsed markdown has headers |

### Implementation: Pure Python (No Extra Libraries)

The chunker is implemented in pure Python — no ML models, no heavy dependencies:

| Task | How |
|------|-----|
| Split by headers | `re.split(r'^#{1,4} .+$', text)` |
| Split by paragraphs | `str.split("\n\n")` |
| Detect tables | `line.startswith("\|")` |
| Group table rows | Simple loop + counter |
| Track chunk size | `len(string)` |
| Metadata per chunk | Python dataclass |

### Chunk Output Format

Each chunk carries metadata for traceability:

```python
Chunk(
    content="## Team Members\n| Name | Role |...",
    metadata={
        "source": "team-wiki.md",
        "section": "Team Members",
        "chunk_index": 2,
        "content_type": "table",  # or "narrative"
        "char_count": 450,
    }
)
```

### Handling Large Documents (500 MB+)

For files that can't fit in memory:

| Document Size | Strategy |
|--------------|----------|
| < 10 MB | Load in memory, split by headers/paragraphs |
| 10-100 MB | Stream page-by-page, track sections as you go |
| 100 MB+ | Stream page-by-page, emit chunks immediately, hold max 2 chunks in memory |

```
Stream page by page → detect headers → track current section → emit chunks
Memory usage: ~10 MB regardless of file size
```

---

## Entity & Relationship Extraction

### Why Extract Entities and Relationships?

After parsing and chunking, we have clean text segments. But text alone can't power a knowledge graph — we need to identify the **entities** (people, services, teams) and **relationships** (who owns what, what depends on what) within that text and structure them as graph-ready data.

### Extraction Approaches Compared

| Approach | What it extracts | Cost | Speed | Accuracy |
|----------|-----------------|------|-------|----------|
| **Rule-based (Regex)** | Emails, dates, IDs, URLs | Free | Instant | 100% for known patterns |
| **NLP Libraries (spaCy)** | People, orgs, locations | Free | Fast | Good for standard entities |
| **Custom NER Models** | Domain-specific entities | Free (after training) | Fast | Excellent (but needs training data) |
| **LLM (Bedrock Claude)** | Entities + relationships + context | $$$ per call | Slow | Best for complex extraction |
| **Hybrid (all of above)** | Everything | $$ (reduced LLM calls) | Mixed | Best overall |

### Rule-Based (Regex)

Hand-written patterns. Fast and free, but only finds what you explicitly code for.

```python
emails = re.findall(r'\b[\w.]+@[\w.]+\.\w+\b', text)   # Finds emails
dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', text)      # Finds dates
```

**Limitation:** Can't understand context. Doesn't know "Plato" is a service vs a philosopher.

### NLP Libraries (spaCy)

Pre-trained Named Entity Recognition models. Runs locally, no API cost.

```python
import spacy
nlp = spacy.load("en_core_web_sm")
doc = nlp("Alice Chen is a Principal Engineer at Amazon")
# Alice Chen → PERSON, Amazon → ORG
```

**Limitation:** Limited types (PERSON, ORG, DATE). Doesn't extract relationships. Misses domain-specific entities.

### LLM-Based (Bedrock Claude)

Prompt an LLM to extract entities and relationships with full context understanding.

```
Input chunk: "Alice Chen owns the Plato Ingestion Service. 
              It depends on Neptune and Bedrock."

LLM Output:
  Entities: [Alice Chen (Person), Plato Ingestion (Service), Neptune (Service), Bedrock (Service)]
  Relationships: [Alice Chen -OWNS-> Plato Ingestion, Plato Ingestion -DEPENDS_ON-> Neptune]
```

**Strength:** Understands context, extracts relationships, handles any domain without training data.

### Our Approach: LLM-First, Optimize Later

```
Phase 1 (Now):   LLM extracts everything — validates the pipeline works
Phase 2 (Later): Add spaCy as first pass (free, extracts obvious entities)
Phase 3 (Later): Add regex for structured patterns (emails, dates, IDs)
Result:          LLM only handles hard cases → 60-80% cost reduction
```

### Entity Extraction Pipeline — Detailed Status

| Sub-component | Status | Details |
|---------------|--------|---------|
| Define entity schema | ⬜ Not started | Node types: Person, Service, Team, Tool, Concept. Relationship types: OWNS, MEMBER_OF, DEPENDS_ON, etc. |
| Bedrock IAM permissions | ⬜ Not started | Add `bedrock:InvokeModel` to bastion IAM role |
| Extraction prompt engineering | ⬜ Not started | Design prompt that tells Claude how to extract entities and relationships |
| Structured output parsing | ⬜ Not started | Parse Claude's JSON response into validated Entity/Relationship objects |
| Single-chunk extraction | ⬜ Not started | Extract entities from one chunk, validate output |
| Multi-chunk extraction | ⬜ Not started | Process all chunks from a document, aggregate entities |
| Entity resolution / dedup | ⬜ Not started | "Alice Chen" and "Alice" → same entity, merge them |
| Confidence scoring | ⬜ Not started | Track LLM confidence for each extraction |
| Error handling & retries | ⬜ Not started | Handle Bedrock throttling, malformed responses, timeouts |
| End-to-end test | ⬜ Not started | Full pipeline: parse → chunk → extract → validate |

---

## License

MIT
