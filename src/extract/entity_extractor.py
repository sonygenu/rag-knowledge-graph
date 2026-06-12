"""
Entity & Relationship Extractor using LLM (Bedrock Claude).

Uses a discovered schema to extract entities and relationships from each chunk.

Usage:
    python -m src.extract.entity_extractor data/sample-team-wiki.md
    python -m src.extract.entity_extractor data/sample-team-wiki.md --schema data/discovered_schema.json
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

MODEL_ID = "anthropic.claude-3-5-haiku-20241022-v1:0"
AWS_REGION = "us-east-1"


@dataclass
class Entity:
    """An extracted entity."""
    name: str
    entity_type: str
    properties: dict = field(default_factory=dict)

    def __repr__(self):
        return f"Entity(name='{self.name}', type='{self.entity_type}')"


@dataclass
class Relationship:
    """An extracted relationship between two entities."""
    from_entity: str
    to_entity: str
    relationship_type: str
    properties: dict = field(default_factory=dict)

    def __repr__(self):
        return f"({self.from_entity}) -[{self.relationship_type}]-> ({self.to_entity})"


@dataclass
class ExtractionResult:
    """Result of entity extraction from a single chunk."""
    entities: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    source_chunk: str = ""
    raw_response: str = ""

    def __repr__(self):
        return f"ExtractionResult(entities={len(self.entities)}, relationships={len(self.relationships)})"


def build_extraction_prompt(schema: dict, chunk_text: str) -> str:
    """
    Build the extraction prompt using the discovered schema.
    """
    entity_types_str = "\n".join(
        f"  - {et['name']}: {et['description']}"
        for et in schema.get("entity_types", [])
    )

    relationship_types_str = "\n".join(
        f"  - {rt['name']}: ({rt['from_type']}) -> ({rt['to_type']}) — {rt['description']}"
        for rt in schema.get("relationship_types", [])
    )

    prompt = f"""You are an entity and relationship extractor for a knowledge graph.

ENTITY TYPES (only extract these types):
{entity_types_str}

RELATIONSHIP TYPES (only extract these types):
{relationship_types_str}

RULES:
- Extract ONLY entities and relationships that are explicitly stated in the text
- Do NOT infer or hallucinate entities that aren't mentioned
- Use the exact entity name as it appears in the text
- Each entity must match one of the defined types
- Each relationship must match one of the defined types
- Include relevant properties for each entity when mentioned in the text

Respond ONLY with valid JSON in this exact format:
{{
    "entities": [
        {{"name": "Entity Name", "type": "EntityType", "properties": {{"key": "value"}}}}
    ],
    "relationships": [
        {{"from": "Entity Name", "to": "Entity Name", "type": "RELATIONSHIP_TYPE", "properties": {{}}}}
    ]
}}

TEXT TO EXTRACT FROM:
---
{chunk_text}
---
"""
    return prompt


def extract_from_chunk(chunk, schema: dict, model_id: str = MODEL_ID) -> ExtractionResult:
    """
    Extract entities and relationships from a single chunk using the schema.
    Includes retry logic with exponential backoff.
    
    Args:
        chunk: A Chunk object from the chunker
        schema: Discovered schema dict with entity_types and relationship_types
        model_id: Bedrock model ID
    
    Returns:
        ExtractionResult with entities and relationships
    """
    prompt = build_extraction_prompt(schema, chunk.content)

    logger.info(f"Extracting from chunk: section='{chunk.metadata.get('section', '?')}', "
                f"chars={len(chunk.content)}")

    raw_text = _call_bedrock_with_retry(prompt, model_id)

    if raw_text is None:
        logger.warning(f"Failed to extract from chunk after retries")
        return ExtractionResult(source_chunk=chunk.metadata.get("section", ""))

    # Parse response
    extraction = _parse_extraction_response(raw_text)
    extraction.source_chunk = chunk.metadata.get("section", "")
    extraction.raw_response = raw_text

    logger.info(f"Extracted: {len(extraction.entities)} entities, "
                f"{len(extraction.relationships)} relationships")

    return extraction


def _call_bedrock_with_retry(prompt: str, model_id: str, max_retries: int = 3) -> str:
    """
    Call Bedrock with exponential backoff and error classification.
    
    Returns the response text, or None if all retries fail.
    """
    import time
    import random
    from botocore.exceptions import ClientError

    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    
    for attempt in range(max_retries):
        try:
            response = client.invoke_model(
                modelId=model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )

            result = json.loads(response["body"].read())
            raw_text = result["content"][0]["text"]
            
            # Check for malformed JSON — if so, retry
            if not _looks_like_json(raw_text):
                logger.warning(f"Attempt {attempt + 1}: LLM returned non-JSON response, retrying...")
                if attempt < max_retries - 1:
                    continue
            
            return raw_text

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            
            # No-retry errors (config problems)
            if error_code in ("AccessDeniedException", "ValidationException"):
                logger.error(f"Non-retryable error: {error_code} — {e}")
                return None

            # Retryable errors
            if error_code in ("ThrottlingException", "ServiceUnavailableException",
                             "ModelTimeoutException", "InternalServerException"):
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries}: {error_code}, "
                    f"retrying in {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
            else:
                logger.error(f"Unexpected error: {error_code} — {e}")
                return None

        except Exception as e:
            logger.error(f"Unexpected exception: {e}")
            return None

    logger.error(f"All {max_retries} attempts failed")
    return None


def _looks_like_json(text: str) -> bool:
    """Quick check if text looks like it contains JSON."""
    stripped = text.strip()
    return stripped.startswith("{") or "{" in stripped


def extract_from_all_chunks(chunks: list, schema: dict, model_id: str = MODEL_ID) -> list:
    """
    Extract entities and relationships from all chunks.
    
    Returns a list of ExtractionResult objects (one per chunk).
    """
    results = []

    for i, chunk in enumerate(chunks):
        logger.info(f"Processing chunk {i+1}/{len(chunks)}")
        try:
            result = extract_from_chunk(chunk, schema, model_id)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to extract from chunk {i+1}: {e}")
            results.append(ExtractionResult(source_chunk=chunk.metadata.get("section", "")))

    return results


def aggregate_results(results: list) -> ExtractionResult:
    """
    Aggregate extraction results from multiple chunks into one.
    Deduplicates entities by name+type.
    """
    all_entities = {}
    all_relationships = []

    for result in results:
        for entity in result.entities:
            key = f"{entity.name}::{entity.entity_type}"
            if key not in all_entities:
                all_entities[key] = entity
            else:
                # Merge properties
                all_entities[key].properties.update(entity.properties)

        all_relationships.extend(result.relationships)

    # Deduplicate relationships
    seen_rels = set()
    unique_rels = []
    for rel in all_relationships:
        key = f"{rel.from_entity}::{rel.relationship_type}::{rel.to_entity}"
        if key not in seen_rels:
            seen_rels.add(key)
            unique_rels.append(rel)

    return ExtractionResult(
        entities=list(all_entities.values()),
        relationships=unique_rels,
    )


def _parse_extraction_response(raw_text: str) -> ExtractionResult:
    """Parse the LLM's JSON response into entities and relationships."""
    import re

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', raw_text)
        if json_match:
            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError:
                logger.error(f"Failed to parse extraction response: {raw_text[:200]}")
                return ExtractionResult()
        else:
            logger.error(f"No JSON found in response: {raw_text[:200]}")
            return ExtractionResult()

    entities = [
        Entity(
            name=e.get("name", ""),
            entity_type=e.get("type", ""),
            properties=e.get("properties", {}),
        )
        for e in data.get("entities", [])
    ]

    relationships = [
        Relationship(
            from_entity=r.get("from", ""),
            to_entity=r.get("to", ""),
            relationship_type=r.get("type", ""),
            properties=r.get("properties", {}),
        )
        for r in data.get("relationships", [])
    ]

    return ExtractionResult(entities=entities, relationships=relationships)


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
    from src.extract.schema_discovery import discover_schema, load_schema, save_schema

    if len(sys.argv) < 2:
        print("Usage: python -m src.extract.entity_extractor <file_path> [--schema <schema.json>]")
        sys.exit(1)

    file_path = sys.argv[1]

    # Check for schema file argument
    schema_path = None
    if "--schema" in sys.argv:
        schema_idx = sys.argv.index("--schema") + 1
        if schema_idx < len(sys.argv):
            schema_path = sys.argv[schema_idx]

    # Step 1: Parse and chunk
    print(f"\n📄 Parsing: {file_path}")
    doc = parse_document(file_path)
    chunks = chunk_document(doc)
    print(f"   Chunks: {len(chunks)}")

    # Step 2: Get schema (discover or load)
    if schema_path:
        print(f"\n📋 Loading schema from: {schema_path}")
        schema = load_schema(schema_path)
    else:
        print(f"\n🔍 Auto-discovering schema...")
        schema = discover_schema(chunks)
        save_schema(schema, "data/discovered_schema.json")

    print(schema.summary())

    # Step 3: Extract entities from all chunks
    print(f"\n⚡ Extracting entities and relationships from {len(chunks)} chunks...\n")
    schema_dict = {
        "entity_types": schema.entity_types,
        "relationship_types": schema.relationship_types,
    }
    results = extract_from_all_chunks(chunks, schema_dict)

    # Step 4: Aggregate
    aggregated = aggregate_results(results)

    # Print results
    print(f"\n{'='*60}")
    print(f"EXTRACTION RESULTS")
    print(f"{'='*60}")
    print(f"\nTotal Entities: {len(aggregated.entities)}")
    print(f"Total Relationships: {len(aggregated.relationships)}")

    print(f"\n--- Entities ---")
    for entity in aggregated.entities:
        props = json.dumps(entity.properties) if entity.properties else ""
        print(f"  [{entity.entity_type}] {entity.name} {props}")

    print(f"\n--- Relationships ---")
    for rel in aggregated.relationships:
        print(f"  {rel}")

    print(f"\n{'='*60}")
