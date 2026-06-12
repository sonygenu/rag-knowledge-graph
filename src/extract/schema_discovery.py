"""
Schema Auto-Discovery using LLM (Bedrock Claude).

Reads sample chunks from a document and asks the LLM to propose
entity types and relationship types — no predefined schema needed.

Usage:
    python -m src.extract.schema_discovery data/sample-team-wiki.md
"""
import json
import logging
from dataclasses import dataclass, field

import boto3

logger = logging.getLogger(__name__)

# Default model — update if different model is available
MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
AWS_REGION = "us-east-1"

DISCOVERY_PROMPT = """You are a knowledge graph schema designer. Your job is to analyze text samples and discover what types of entities and relationships exist.

Read the following text samples carefully. Then propose:
1. Entity types — categories of things mentioned (e.g., Person, Service, Team)
2. Relationship types — how entities connect to each other

Rules:
- Keep entity types broad but meaningful (5-10 types max)
- Each relationship must specify which entity types it connects
- Use UPPER_SNAKE_CASE for relationship names
- Include a brief description for each type
- Only propose types that actually appear in the text

Respond ONLY with valid JSON in this exact format:
{
    "entity_types": [
        {"name": "TypeName", "description": "What this type represents", "example_properties": ["prop1", "prop2"]}
    ],
    "relationship_types": [
        {"name": "RELATIONSHIP_NAME", "from_type": "EntityType", "to_type": "EntityType", "description": "What this relationship means"}
    ]
}

TEXT SAMPLES:
---
"""


@dataclass
class DiscoveredSchema:
    """The schema proposed by the LLM from document analysis."""
    entity_types: list = field(default_factory=list)
    relationship_types: list = field(default_factory=list)
    raw_response: str = ""

    def __repr__(self):
        return (
            f"DiscoveredSchema(entities={len(self.entity_types)}, "
            f"relationships={len(self.relationship_types)})"
        )

    def to_json(self) -> str:
        return json.dumps({
            "entity_types": self.entity_types,
            "relationship_types": self.relationship_types,
        }, indent=2)

    def summary(self) -> str:
        lines = ["\n📊 Discovered Schema:\n"]
        lines.append("  Entity Types:")
        for et in self.entity_types:
            props = ", ".join(et.get("example_properties", []))
            lines.append(f"    • {et['name']} — {et['description']} [{props}]")
        lines.append("\n  Relationship Types:")
        for rt in self.relationship_types:
            lines.append(
                f"    • ({rt['from_type']}) -[{rt['name']}]-> ({rt['to_type']}) — {rt['description']}"
            )
        return "\n".join(lines)


def discover_schema(chunks: list, model_id: str = MODEL_ID, max_samples: int = 5) -> DiscoveredSchema:
    """
    Auto-discover entity and relationship types from sample chunks.
    
    Args:
        chunks: List of Chunk objects from the chunker
        model_id: Bedrock model ID
        max_samples: Number of chunks to sample (3-5 recommended)
    
    Returns:
        DiscoveredSchema with proposed entity and relationship types
    """
    # Select representative samples (first, middle, last)
    if len(chunks) <= max_samples:
        samples = chunks
    else:
        step = len(chunks) // max_samples
        samples = [chunks[i * step] for i in range(max_samples)]

    # Build the prompt with sample text
    sample_text = ""
    for i, chunk in enumerate(samples, 1):
        sample_text += f"\n--- Sample {i} (from {chunk.metadata.get('section', 'unknown')}) ---\n"
        sample_text += chunk.content + "\n"

    full_prompt = DISCOVERY_PROMPT + sample_text

    logger.info(f"Discovering schema from {len(samples)} sample chunks using {model_id}")

    # Call Bedrock
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": full_prompt}]
        })
    )

    result = json.loads(response["body"].read())
    raw_text = result["content"][0]["text"]

    logger.info(f"LLM response received ({len(raw_text)} chars)")

    # Parse the JSON response
    schema = _parse_schema_response(raw_text)
    schema.raw_response = raw_text

    logger.info(f"Discovered: {len(schema.entity_types)} entity types, "
                f"{len(schema.relationship_types)} relationship types")

    return schema


def _parse_schema_response(raw_text: str) -> DiscoveredSchema:
    """Parse the LLM's JSON response into a DiscoveredSchema."""
    # Try to extract JSON from the response (LLM may include extra text)
    try:
        # Try direct parse first
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # Try to find JSON block in the response
        import re
        json_match = re.search(r'\{[\s\S]*\}', raw_text)
        if json_match:
            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError:
                logger.error(f"Failed to parse LLM response as JSON: {raw_text[:200]}")
                return DiscoveredSchema()
        else:
            logger.error(f"No JSON found in LLM response: {raw_text[:200]}")
            return DiscoveredSchema()

    return DiscoveredSchema(
        entity_types=data.get("entity_types", []),
        relationship_types=data.get("relationship_types", []),
    )


def save_schema(schema: DiscoveredSchema, output_path: str):
    """Save discovered schema to a JSON file for review."""
    with open(output_path, "w") as f:
        f.write(schema.to_json())
    logger.info(f"Schema saved to {output_path}")


def load_schema(schema_path: str) -> DiscoveredSchema:
    """Load a previously discovered/edited schema."""
    with open(schema_path, "r") as f:
        data = json.loads(f.read())
    return DiscoveredSchema(
        entity_types=data.get("entity_types", []),
        relationship_types=data.get("relationship_types", []),
    )


# --- CLI ---

if __name__ == "__main__":
    import os
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    from src.ingest.loader import parse_document
    from src.ingest.chunker import chunk_document

    if len(sys.argv) < 2:
        print("Usage: python -m src.extract.schema_discovery <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]

    # Parse and chunk
    print(f"\n📄 Parsing: {file_path}")
    doc = parse_document(file_path)
    chunks = chunk_document(doc)
    print(f"   Chunks: {len(chunks)}")

    # Discover schema
    print(f"\n🔍 Discovering schema from sample chunks...")
    schema = discover_schema(chunks)

    # Print results
    print(schema.summary())

    # Save to file
    output_path = "data/discovered_schema.json"
    save_schema(schema, output_path)
    print(f"\n💾 Schema saved to: {output_path}")
    print("   Review and edit this file, then use it for extraction.")
