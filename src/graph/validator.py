"""
Graph Schema Validator — Verifies the loaded graph matches the expected schema.

Runs after loading and reports:
- Schema compliance (all labels/types match discovered schema)
- Orphan nodes (no relationships)
- Dangling chunks (not linked to any entity)
- Duplicate entities (case/whitespace mismatches)
- Relationship direction correctness
- Graph stats summary

Usage:
    python -m src.graph.validator                              # Validate with no schema
    python -m src.graph.validator --schema data/discovered_schema.json  # Validate against schema
"""
import logging
from collections import Counter

from src.graph.neptune_client import NeptuneClient

logger = logging.getLogger(__name__)


class GraphValidator:
    """Validates the graph in Neptune against the expected schema."""

    def __init__(self, client: NeptuneClient = None):
        self.client = client or NeptuneClient()
        self.issues = []  # Collected issues

    # --- Step 1: Schema Compliance ---

    def validate_schema_compliance(self, schema: dict = None) -> list:
        """
        Check all node labels and relationship types exist in the schema.
        
        Flags any types that the LLM created but weren't in the discovered schema.
        """
        issues = []

        # Get all node labels from graph
        node_results = self.client.execute_query(
            "MATCH (n) RETURN DISTINCT labels(n) AS labels"
        )
        graph_labels = set()
        for r in node_results:
            for label in r.get("labels", []):
                graph_labels.add(label)

        # Get all relationship types from graph
        rel_results = self.client.execute_query(
            "MATCH ()-[r]->() RETURN DISTINCT type(r) AS type"
        )
        graph_rel_types = set(r.get("type", "") for r in rel_results)

        if schema:
            # Check against discovered schema
            schema_labels = set(et["name"] for et in schema.get("entity_types", []))
            schema_labels.add("Chunk")  # Chunks are always valid
            schema_labels.add("Document")  # Documents are always valid

            schema_rel_types = set(rt["name"] for rt in schema.get("relationship_types", []))
            schema_rel_types.add("MENTIONS")  # Always valid
            schema_rel_types.add("FROM_DOCUMENT")  # Always valid

            unexpected_labels = graph_labels - schema_labels
            unexpected_rels = graph_rel_types - schema_rel_types

            if unexpected_labels:
                issues.append(f"⚠️  Unexpected node labels (not in schema): {unexpected_labels}")
            if unexpected_rels:
                issues.append(f"⚠️  Unexpected relationship types (not in schema): {unexpected_rels}")

            if not unexpected_labels and not unexpected_rels:
                issues.append("✅ All node labels and relationship types match schema")
        else:
            issues.append(f"ℹ️  Node labels in graph: {graph_labels}")
            issues.append(f"ℹ️  Relationship types in graph: {graph_rel_types}")

        return issues

    # --- Step 2: Orphan Nodes ---

    def find_orphan_nodes(self) -> list:
        """
        Find nodes with zero relationships (completely isolated).
        
        Orphan nodes are unreachable during graph traversal.
        """
        issues = []

        results = self.client.execute_query("""
            MATCH (n)
            WHERE NOT (n)--()
            RETURN labels(n) AS labels, n.name AS name
            LIMIT 20
        """)

        if results:
            issues.append(f"⚠️  {len(results)} orphan node(s) (no relationships):")
            for r in results:
                issues.append(f"     [{r.get('labels')}] {r.get('name', 'unnamed')}")
        else:
            issues.append("✅ No orphan nodes — all nodes have at least one relationship")

        return issues

    # --- Step 3: Dangling Chunks ---

    def find_dangling_chunks(self) -> list:
        """
        Find :Chunk nodes that have no [:MENTIONS] edges.
        
        These chunks are loaded but not linked to any entity — unreachable during retrieval.
        """
        issues = []

        results = self.client.execute_query("""
            MATCH (c:Chunk)
            WHERE NOT (c)-[:MENTIONS]->()
            RETURN c.id AS id, c.section AS section
            LIMIT 20
        """)

        if results:
            issues.append(f"⚠️  {len(results)} chunk(s) with no MENTIONS links:")
            for r in results:
                issues.append(f"     Chunk {r.get('id')} (section: {r.get('section', '?')})")
        else:
            issues.append("✅ All chunks are linked to at least one entity")

        return issues

    # --- Step 4: Duplicate Entities ---

    def find_duplicate_entities(self) -> list:
        """
        Find entity names that differ only by case or whitespace.
        
        These should be merged (e.g., "Alice Chen" and "alice chen").
        """
        issues = []

        results = self.client.execute_query("""
            MATCH (n)
            WHERE n.name IS NOT NULL
            RETURN n.name AS name, labels(n) AS labels
        """)

        # Group by lowercase name
        name_groups = {}
        for r in results:
            name = r.get("name", "")
            key = name.lower().strip()
            if key not in name_groups:
                name_groups[key] = []
            name_groups[key].append(name)

        # Find duplicates
        duplicates = {k: v for k, v in name_groups.items() if len(v) > 1}

        if duplicates:
            issues.append(f"❌ {len(duplicates)} duplicate entity name(s) found:")
            for key, names in duplicates.items():
                issues.append(f"     {names} — should be merged")
        else:
            issues.append("✅ No duplicate entity names detected")

        return issues

    # --- Step 5: Relationship Direction Check ---

    def validate_relationship_directions(self, schema: dict = None) -> list:
        """
        Verify relationship directions match schema expectations.
        
        E.g., OWNS should go Person→Service, not Service→Person.
        """
        issues = []

        if not schema or not schema.get("relationship_types"):
            issues.append("ℹ️  No schema provided — skipping direction validation")
            return issues

        for rt in schema["relationship_types"]:
            rel_name = rt["name"]
            expected_from = rt.get("from_type", "")
            expected_to = rt.get("to_type", "")

            if not expected_from or not expected_to:
                continue

            # Check if any relationships go in the wrong direction
            results = self.client.execute_query(f"""
                MATCH (a)-[r:`{rel_name}`]->(b)
                RETURN labels(a) AS from_labels, labels(b) AS to_labels
                LIMIT 5
            """)

            wrong_direction = 0
            for r in results:
                from_labels = r.get("from_labels", [])
                to_labels = r.get("to_labels", [])
                if expected_from not in from_labels or expected_to not in to_labels:
                    wrong_direction += 1

            if wrong_direction > 0:
                issues.append(
                    f"⚠️  {rel_name}: {wrong_direction} edge(s) may have wrong direction "
                    f"(expected {expected_from}→{expected_to})"
                )

        if not any("⚠️" in i for i in issues):
            issues.append("✅ All relationship directions match schema")

        return issues

    # --- Step 6: Graph Stats ---

    def get_graph_stats(self) -> list:
        """Summary stats: nodes per label, relationships per type."""
        stats = []

        # Nodes by label
        node_results = self.client.execute_query(
            "MATCH (n) RETURN labels(n) AS labels, count(n) AS count ORDER BY count DESC"
        )
        stats.append("📊 Nodes by label:")
        for r in node_results:
            stats.append(f"     {r.get('labels')}: {r.get('count')}")

        # Relationships by type
        rel_results = self.client.execute_query(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC"
        )
        stats.append("📊 Relationships by type:")
        for r in rel_results:
            stats.append(f"     {r.get('type')}: {r.get('count')}")

        # Totals
        total_nodes = self.client.count_nodes()
        total_rels = self.client.count_relationships()
        stats.append(f"📊 Totals: {total_nodes} nodes, {total_rels} relationships")

        return stats

    # --- Step 7: Run All Validations ---

    def run_all_validations(self, schema: dict = None) -> dict:
        """
        Run all validation checks and print a report.
        
        Returns dict with all issues categorized.
        """
        print(f"\n{'='*60}")
        print("🔍 GRAPH VALIDATION REPORT")
        print(f"{'='*60}")

        all_issues = {}

        # Stats
        print("\n--- Graph Stats ---")
        stats = self.get_graph_stats()
        for s in stats:
            print(f"  {s}")

        # Schema compliance
        print("\n--- Schema Compliance ---")
        compliance = self.validate_schema_compliance(schema)
        all_issues["schema_compliance"] = compliance
        for i in compliance:
            print(f"  {i}")

        # Orphan nodes
        print("\n--- Orphan Nodes ---")
        orphans = self.find_orphan_nodes()
        all_issues["orphan_nodes"] = orphans
        for i in orphans:
            print(f"  {i}")

        # Dangling chunks
        print("\n--- Dangling Chunks ---")
        dangling = self.find_dangling_chunks()
        all_issues["dangling_chunks"] = dangling
        for i in dangling:
            print(f"  {i}")

        # Duplicates
        print("\n--- Duplicate Entities ---")
        duplicates = self.find_duplicate_entities()
        all_issues["duplicates"] = duplicates
        for i in duplicates:
            print(f"  {i}")

        # Direction check
        print("\n--- Relationship Directions ---")
        directions = self.validate_relationship_directions(schema)
        all_issues["directions"] = directions
        for i in directions:
            print(f"  {i}")

        # Summary
        print(f"\n{'='*60}")
        error_count = sum(1 for issues in all_issues.values() for i in issues if "❌" in i)
        warning_count = sum(1 for issues in all_issues.values() for i in issues if "⚠️" in i)
        pass_count = sum(1 for issues in all_issues.values() for i in issues if "✅" in i)

        print(f"  ✅ Passed: {pass_count}  ⚠️ Warnings: {warning_count}  ❌ Errors: {error_count}")
        print(f"{'='*60}\n")

        return all_issues


# --- CLI ---

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Load schema if provided
    schema = None
    if "--schema" in sys.argv:
        schema_idx = sys.argv.index("--schema") + 1
        if schema_idx < len(sys.argv):
            from src.extract.schema_discovery import load_schema
            schema_obj = load_schema(sys.argv[schema_idx])
            schema = {
                "entity_types": schema_obj.entity_types,
                "relationship_types": schema_obj.relationship_types,
            }
            print(f"Loaded schema from: {sys.argv[schema_idx]}")

    validator = GraphValidator()
    validator.run_all_validations(schema)
