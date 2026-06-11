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
| Multi-format testing | ✅ Complete | Tested with .md, .txt, .html on bastion |
| Chunking | ⬜ Not started | Split parsed docs into segments |
| PDF parsing with OCR | ⬜ Not started | Scanned PDF support via RapidOCR |
| S3 integration | ⬜ Not started | Load documents from S3 buckets |
| Batch processing | ⬜ Not started | Process large document sets |

---

## License

MIT
