"""
Graph Loader — Writes extracted entities and relationships to Neptune.

Takes output from entity extraction and creates:
- Entity nodes (Person, Service, Team, etc.) with properties
- Relationship edges (OWNS, MEMBER_OF, DEPENDS_ON) between nodes
- Chunk nodes with text for retrieval
- MENTIONS edges linking chunks to the entities they contain

Uses MERGE (upsert) for idempotency — safe to re-run without duplicates.

Usage:
    python -m src.graph.loader data/sample-team-wiki.md
"""
import json
import logging
import hashlib
from typing import List

from src.graph.neptune_client import NeptuneClient
from src.extract.entity_extractor import Entity, Relationship, ExtractionResult
from src.ingest.chunker import Chunk

logger = logging.getLogger(__name__)


class GraphLoader:
    """
    Loads entities, relationships, and chunks into Neptune.
    Uses MERGE for idempotent upserts — running twice won't create duplicates.
    Supports batch loading — multiple entities/relationships per Neptune call.
    """

    def __init__(self, client: NeptuneClient = None, batch_size: int = 10):
        self.client = client or NeptuneClient()
        self.batch_size = batch_size
        self._stats = {"nodes_created": 0, "relationships_created": 0, "chunks_created": 0}

    # --- Step 1: Load Entity Nodes (Batched) ---

    def load_entities(self, entities: List[Entity]) -> int:
        """
        Create entity nodes in Neptune using batched MERGE (upsert).
        
        Groups entities by type and loads in batches of self.batch_size.
        Each batch is a single Neptune call using UNWIND.
        
        Returns: number of entities loaded
        """
        # Group entities by type (UNWIND works best with same label)
        by_type = {}
        for entity in entities:
            if not entity.name or not entity.entity_type:
                logger.warning(f"Skipping entity with missing name or type: {entity}")
                continue
            by_type.setdefault(entity.entity_type, []).append(entity)

        count = 0
        for entity_type, type_entities in by_type.items():
            # Process in batches
            for i in range(0, len(type_entities), self.batch_size):
                batch = type_entities[i:i + self.batch_size]
                batch_count = self._batch_merge_entities(entity_type, batch)
                count += batch_count

        self._stats["nodes_created"] += count
        logger.info(f"Loaded {count}/{len(entities)} entity nodes (batch_size={self.batch_size})")
        return count

    def _batch_merge_entities(self, entity_type: str, batch: List[Entity]) -> int:
        """
        MERGE a batch of entities of the same type in a single Neptune call.
        
        Uses UNWIND to process a list of entities in one query:
          UNWIND [{name:'Alice', role:'Engineer'}, ...] AS props
          MERGE (n:Person {name: props.name})
          SET n += props
        """
        # Build the list of property maps
        entity_maps = []
        for entity in batch:
            props = {"name": entity.name}
            props.update({k: str(v) for k, v in entity.properties.items()})
            entity_maps.append(props)

        # UNWIND query — processes entire batch in one call
        query = f"""
            UNWIND {json.dumps(entity_maps)} AS props
            MERGE (n:`{entity_type}` {{name: props.name}})
            SET n += props
            RETURN count(n) AS loaded
        """

        try:
            result = self.client.execute_query(query)
            loaded = result[0]["loaded"] if result else 0
            logger.debug(f"  Batch loaded {loaded} [{entity_type}] nodes")
            return len(batch)
        except Exception as e:
            logger.error(f"  Batch failed for [{entity_type}]: {e}")
            # Fallback: try one by one
            return self._fallback_load_entities(entity_type, batch)

    def _fallback_load_entities(self, entity_type: str, batch: List[Entity]) -> int:
        """Fallback: load entities one by one if batch fails."""
        count = 0
        for entity in batch:
            props = {"name": entity.name}
            props.update(entity.properties)
            set_clause = ", ".join([f"n.`{k}` = '{v}'" for k, v in props.items()])
            query = f"""
                MERGE (n:`{entity_type}` {{name: '{entity.name}'}})
                SET {set_clause}
                RETURN n.name AS name
            """
            try:
                self.client.execute_query(query)
                count += 1
            except Exception as e:
                logger.error(f"  Failed to load entity {entity.name}: {e}")
        return count

    # --- Step 2: Load Relationship Edges (Batched) ---

    def load_relationships(self, relationships: List[Relationship]) -> int:
        """
        Create relationship edges in Neptune using batched MERGE.
        
        Groups by relationship type and loads in batches.
        
        Returns: number of relationships loaded
        """
        # Group by relationship type
        by_type = {}
        for rel in relationships:
            if not rel.from_entity or not rel.to_entity or not rel.relationship_type:
                logger.warning(f"Skipping relationship with missing data: {rel}")
                continue
            by_type.setdefault(rel.relationship_type, []).append(rel)

        count = 0
        for rel_type, type_rels in by_type.items():
            for i in range(0, len(type_rels), self.batch_size):
                batch = type_rels[i:i + self.batch_size]
                batch_count = self._batch_merge_relationships(rel_type, batch)
                count += batch_count

        self._stats["relationships_created"] += count
        logger.info(f"Loaded {count}/{len(relationships)} relationships (batch_size={self.batch_size})")
        return count

    def _batch_merge_relationships(self, rel_type: str, batch: List[Relationship]) -> int:
        """
        MERGE a batch of relationships of the same type in a single Neptune call.
        
        Uses UNWIND to process multiple relationships at once.
        """
        rel_maps = [
            {"from_name": rel.from_entity, "to_name": rel.to_entity}
            for rel in batch
        ]

        query = f"""
            UNWIND {json.dumps(rel_maps)} AS rel
            MATCH (from {{name: rel.from_name}})
            MATCH (to {{name: rel.to_name}})
            MERGE (from)-[r:`{rel_type}`]->(to)
            RETURN count(r) AS loaded
        """

        try:
            result = self.client.execute_query(query)
            loaded = result[0]["loaded"] if result else 0
            logger.debug(f"  Batch loaded {loaded} [{rel_type}] relationships")
            return len(batch)
        except Exception as e:
            logger.error(f"  Batch failed for [{rel_type}]: {e}")
            # Fallback: one by one
            return self._fallback_load_relationships(batch)

    def _fallback_load_relationships(self, batch: List[Relationship]) -> int:
        """Fallback: load relationships one by one if batch fails."""
        count = 0
        for rel in batch:
            query = f"""
                MATCH (from {{name: '{rel.from_entity}'}})
                MATCH (to {{name: '{rel.to_entity}'}})
                MERGE (from)-[r:`{rel.relationship_type}`]->(to)
                RETURN from.name AS from_name, to.name AS to_name
            """
            try:
                result = self.client.execute_query(query)
                if result:
                    count += 1
            except Exception as e:
                logger.error(f"  Failed: {rel}: {e}")
        return count

    # --- Step 3: Load Chunk Nodes ---

    def load_chunks(self, chunks: List[Chunk]) -> int:
        """
        Create chunk nodes in Neptune for retrieval.
        
        Each chunk becomes a (:Chunk) node with:
        - Unique ID (hash of content)
        - Text content
        - Source metadata
        
        Returns: number of chunks loaded
        """
        count = 0
        for chunk in chunks:
            # Generate a unique ID from content hash
            chunk_id = hashlib.md5(chunk.content.encode()).hexdigest()[:12]
            source = chunk.metadata.get("source", "unknown")
            section = chunk.metadata.get("section", "unknown")

            # Escape single quotes in text
            safe_text = chunk.content.replace("'", "\\'")[:2000]  # Limit text size

            query = f"""
                MERGE (c:Chunk {{id: '{chunk_id}'}})
                SET c.text = '{safe_text}',
                    c.source = '{source}',
                    c.section = '{section}',
                    c.char_count = {len(chunk.content)}
                RETURN c.id AS id
            """

            try:
                self.client.execute_query(query)
                count += 1
                chunk.metadata["chunk_id"] = chunk_id  # Store ID for linking
                logger.debug(f"  Loaded chunk: {chunk_id} (section: {section})")
            except Exception as e:
                logger.error(f"  Failed to load chunk {chunk_id}: {e}")

        self._stats["chunks_created"] += count
        logger.info(f"Loaded {count}/{len(chunks)} chunk nodes")
        return count

    # --- Step 4: Link Chunks to Entities ---

    def link_chunks_to_entities(self, chunks: List[Chunk], entities: List[Entity]) -> int:
        """
        Create [:MENTIONS] edges from chunk nodes to entity nodes.
        
        For each chunk, checks which entities are mentioned in its text
        and creates MENTIONS edges.
        
        Returns: number of links created
        """
        count = 0
        entity_names = [e.name for e in entities if e.name]

        for chunk in chunks:
            chunk_id = chunk.metadata.get("chunk_id")
            if not chunk_id:
                continue

            # Check which entities are mentioned in this chunk's text
            for entity_name in entity_names:
                if entity_name.lower() in chunk.content.lower():
                    query = f"""
                        MATCH (c:Chunk {{id: '{chunk_id}'}})
                        MATCH (e {{name: '{entity_name}'}})
                        MERGE (c)-[r:MENTIONS]->(e)
                        RETURN c.id AS chunk, e.name AS entity
                    """

                    try:
                        result = self.client.execute_query(query)
                        if result:
                            count += 1
                            logger.debug(f"  Linked: Chunk({chunk_id}) -[MENTIONS]-> {entity_name}")
                    except Exception as e:
                        logger.error(f"  Failed to link chunk {chunk_id} to {entity_name}: {e}")

        logger.info(f"Created {count} MENTIONS links")
        return count

    # --- Step 5: High-Level Orchestrator ---

    def load_extraction_result(self, extraction: ExtractionResult, chunks: List[Chunk] = None) -> dict:
        """
        Load a complete extraction result into Neptune.
        
        Orchestrates: entities → relationships → chunks → links
        
        Args:
            extraction: ExtractionResult with entities and relationships
            chunks: Optional list of Chunk objects to store as nodes
        
        Returns:
            dict with loading stats
        """
        logger.info("=" * 50)
        logger.info("Starting graph loading...")
        logger.info(f"  Entities to load: {len(extraction.entities)}")
        logger.info(f"  Relationships to load: {len(extraction.relationships)}")
        logger.info(f"  Chunks to load: {len(chunks) if chunks else 0}")
        logger.info("=" * 50)

        # Step 1: Load entity nodes
        print(f"\n📌 Loading {len(extraction.entities)} entity nodes...")
        self.load_entities(extraction.entities)

        # Step 2: Load relationship edges
        print(f"🔗 Loading {len(extraction.relationships)} relationships...")
        self.load_relationships(extraction.relationships)

        # Step 3: Load chunk nodes (optional)
        if chunks:
            print(f"📄 Loading {len(chunks)} chunk nodes...")
            self.load_chunks(chunks)

            # Step 4: Link chunks to entities
            print(f"🔗 Linking chunks to entities...")
            self.link_chunks_to_entities(chunks, extraction.entities)

        # Summary
        print(f"\n{'='*50}")
        print(f"✅ Graph loading complete!")
        print(f"   Nodes created: {self._stats['nodes_created']}")
        print(f"   Relationships created: {self._stats['relationships_created']}")
        print(f"   Chunks created: {self._stats['chunks_created']}")
        print(f"{'='*50}")

        return self._stats


# --- CLI: Full End-to-End Pipeline ---

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
    from src.extract.entity_extractor import extract_from_all_chunks, aggregate_results

    if len(sys.argv) < 2:
        print("Usage: python -m src.graph.loader <file_path> [--schema <schema.json>]")
        sys.exit(1)

    file_path = sys.argv[1]

    # Check for schema file
    schema_path = None
    if "--schema" in sys.argv:
        schema_idx = sys.argv.index("--schema") + 1
        if schema_idx < len(sys.argv):
            schema_path = sys.argv[schema_idx]

    # --- Full Pipeline ---
    print(f"\n🚀 FULL PIPELINE: {file_path}")
    print(f"{'='*60}\n")

    # Step 1: Parse
    print("📄 Step 1: Parsing document...")
    doc = parse_document(file_path)
    print(f"   Parsed: {doc.source} ({len(doc.markdown)} chars)\n")

    # Step 2: Chunk
    print("✂️  Step 2: Chunking...")
    chunks = chunk_document(doc)
    print(f"   Chunks: {len(chunks)}\n")

    # Step 3: Schema discovery
    if schema_path:
        print(f"📋 Step 3: Loading schema from {schema_path}...")
        schema = load_schema(schema_path)
    else:
        print("🔍 Step 3: Auto-discovering schema...")
        schema = discover_schema(chunks)
        save_schema(schema, "data/discovered_schema.json")
    print(f"   Entity types: {len(schema.entity_types)}")
    print(f"   Relationship types: {len(schema.relationship_types)}\n")

    # Step 4: Extract entities
    print("⚡ Step 4: Extracting entities and relationships...")
    schema_dict = {
        "entity_types": schema.entity_types,
        "relationship_types": schema.relationship_types,
    }
    results = extract_from_all_chunks(chunks, schema_dict)
    aggregated = aggregate_results(results)
    print(f"   Entities: {len(aggregated.entities)}")
    print(f"   Relationships: {len(aggregated.relationships)}\n")

    # Step 5: Load to Neptune
    print("🔗 Step 5: Loading to Neptune...")
    loader = GraphLoader()
    stats = loader.load_extraction_result(aggregated, chunks)

    # Step 6: Verify
    print(f"\n🔍 Step 6: Verifying graph state...")
    client = NeptuneClient()
    total_nodes = client.count_nodes()
    total_rels = client.count_relationships()
    print(f"   Neptune now has: {total_nodes} nodes, {total_rels} relationships")
    print(f"\n🎉 Pipeline complete!")
