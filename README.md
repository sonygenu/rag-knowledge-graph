# RAG Knowledge Graph

A Retrieval-Augmented Generation system powered by Neo4j knowledge graphs for accurate, context-rich AI responses.

---

## Why Knowledge Graphs Matter for RAG

### The Problem with Vanilla RAG

Standard RAG works like this: chunk documents → embed them → retrieve top-k by vector similarity → feed to LLM. It works well for "find me relevant passages" but breaks down when questions require:

- **Relationships between entities** — "What projects is Alice working on that depend on Service X?"
- **Multi-hop reasoning** — "What team owns the service that feeds this pipeline?"
- **Structured facts** — "Who is the on-call for this alarm right now?"
- **Disambiguation** — "Which 'Plato' — the ingestion service or the philosopher?"

Vector similarity retrieves semantically close text — but it has no concept of connections.

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

## Architecture (Planned)

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

- **Graph Database:** Neo4j
- **LLM:** AWS Bedrock (Claude)
- **Entity Extraction:** LLM-powered with structured output
- **Vector Search:** Neo4j vector index
- **Framework:** LangChain / LlamaIndex
- **Language:** Python

---

## Project Status

🚧 **In Progress** — building incrementally. This README will be updated as components are added.

| Component | Status |
|-----------|--------|
| Project setup | ✅ |
| Document ingestion pipeline | ⬜ |
| Entity/relationship extraction | ⬜ |
| Neo4j graph schema & loading | ⬜ |
| Query engine (NL → Cypher) | ⬜ |
| Hybrid retrieval (graph + vector) | ⬜ |
| RAG chain with LLM | ⬜ |
| Evaluation & benchmarks | ⬜ |

---

## License

MIT
