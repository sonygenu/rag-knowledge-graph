"""
Neptune Client — Authenticated openCypher interface to Amazon Neptune.

Uses boto3 neptunedata client (handles SigV4 signing automatically).

Handles:
- IAM SigV4 authentication (automatic via boto3)
- openCypher query execution
- Parameterized queries
- Connection health checks
- Retry on transient failures

Usage:
    from src.graph.neptune_client import NeptuneClient
    
    client = NeptuneClient()
    result = client.execute_query("MATCH (n) RETURN count(n) AS total")
    print(result)

Prerequisites:
    - Neptune endpoint configured in .env or environment variables
    - IAM role with neptune-db:* permissions
    - Network access to Neptune (run from bastion)
"""
import os
import json
import logging
import time
import random

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Configuration — loaded from environment or defaults
NEPTUNE_ENDPOINT = os.getenv(
    "NEPTUNE_ENDPOINT",
    "https://db-neptune-1.cluster-chcfphprbn4n.us-east-1.neptune.amazonaws.com:8182"
)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


class NeptuneClient:
    """
    Client for executing openCypher queries against Amazon Neptune.
    
    Uses boto3 neptunedata client — handles SigV4 signing automatically.
    Designed to run from an EC2 instance with an IAM role that has Neptune access.
    """

    def __init__(self, endpoint: str = None, region: str = None):
        self.endpoint = endpoint or NEPTUNE_ENDPOINT
        self.region = region or AWS_REGION

        # boto3 handles SigV4 signing automatically
        self._client = boto3.client(
            "neptunedata",
            region_name=self.region,
            endpoint_url=self.endpoint,
        )

        logger.info(f"NeptuneClient initialized: {self.endpoint} ({self.region})")

    def execute_query(self, query: str, parameters: dict = None, max_retries: int = 3) -> list:
        """
        Execute an openCypher query against Neptune.
        
        Args:
            query: openCypher query string (e.g., "MATCH (n:Person) RETURN n.name")
            parameters: Optional dict of query parameters (safe from injection)
            max_retries: Number of retry attempts for transient failures
        
        Returns:
            List of result rows (each row is a dict)
        
        Example:
            results = client.execute_query(
                "MATCH (p:Person {name: $name}) RETURN p",
                parameters={"name": "Alice Chen"}
            )
        """
        for attempt in range(max_retries):
            try:
                kwargs = {"openCypherQuery": query}
                if parameters:
                    kwargs["parameters"] = json.dumps(parameters)

                response = self._client.execute_open_cypher_query(**kwargs)
                return response.get("results", [])

            except ClientError as e:
                error_code = e.response["Error"]["Code"]

                # Don't retry auth or validation errors
                if error_code in ("AccessDeniedException",):
                    logger.error(f"Access denied: {e}")
                    raise PermissionError(f"Neptune access denied: {e}")

                if error_code in ("MalformedQueryException", "BadRequestException"):
                    logger.error(f"Query error: {e}")
                    raise ValueError(f"Invalid openCypher query: {e}")

                # Retry on transient errors
                if error_code in ("ThrottlingException", "InternalFailureException",
                                 "TooManyRequestsException", "ServiceUnavailableException"):
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries}: {error_code}, "
                        f"retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Unexpected error: {error_code} — {e}")
                    raise

            except Exception as e:
                logger.error(f"Unexpected exception: {e}")
                raise

        raise RuntimeError(f"Failed to execute query after {max_retries} attempts")

    def health_check(self) -> dict:
        """
        Check if Neptune is reachable and responding.
        
        Returns:
            dict with status info, or raises an exception
        """
        try:
            result = self.execute_query("RETURN 1 AS health_check", max_retries=1)
            return {"status": "healthy", "result": result}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def count_nodes(self, label: str = None) -> int:
        """Count nodes in the graph, optionally filtered by label."""
        if label:
            query = f"MATCH (n:`{label}`) RETURN count(n) AS total"
        else:
            query = "MATCH (n) RETURN count(n) AS total"

        result = self.execute_query(query)
        return result[0]["total"] if result else 0

    def count_relationships(self, rel_type: str = None) -> int:
        """Count relationships in the graph, optionally filtered by type."""
        if rel_type:
            query = f"MATCH ()-[r:`{rel_type}`]->() RETURN count(r) AS total"
        else:
            query = "MATCH ()-[r]->() RETURN count(r) AS total"

        result = self.execute_query(query)
        return result[0]["total"] if result else 0

    def get_schema_summary(self) -> dict:
        """Get a summary of what's in the graph (node counts, relationship counts)."""
        return {
            "total_nodes": self.count_nodes(),
            "total_relationships": self.count_relationships(),
        }


# --- CLI ---

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    print("\n🔗 Testing Neptune Client\n")

    client = NeptuneClient()

    # Health check
    print("1. Health check...")
    health = client.health_check()
    print(f"   Status: {health['status']}")

    if health["status"] == "healthy":
        # Count nodes
        print("\n2. Counting nodes...")
        total_nodes = client.count_nodes()
        print(f"   Total nodes: {total_nodes}")

        # Count relationships
        print("\n3. Counting relationships...")
        total_rels = client.count_relationships()
        print(f"   Total relationships: {total_rels}")

        # Schema summary
        print("\n4. Graph schema summary...")
        summary = client.get_schema_summary()
        print(f"   {summary}")

        print(f"\n✅ Neptune client working!")
    else:
        print(f"\n❌ Neptune is unhealthy: {health.get('error')}")
