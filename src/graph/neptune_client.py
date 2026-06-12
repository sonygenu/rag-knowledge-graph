"""
Neptune Client — Authenticated openCypher interface to Amazon Neptune.

Handles:
- IAM SigV4 authentication (no passwords, uses AWS credentials)
- openCypher query execution
- Parameterized queries (safe from injection)
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
from typing import Optional
from urllib.parse import urlencode

import boto3
import requests
from requests_aws4auth import AWS4Auth

logger = logging.getLogger(__name__)

# Configuration — loaded from environment or defaults
NEPTUNE_ENDPOINT = os.getenv(
    "NEPTUNE_ENDPOINT",
    "db-neptune-1.cluster-chcfphprbn4n.us-east-1.neptune.amazonaws.com"
)
NEPTUNE_PORT = int(os.getenv("NEPTUNE_PORT", "8182"))
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


class NeptuneClient:
    """
    Client for executing openCypher queries against Amazon Neptune.
    
    Uses IAM SigV4 signing for authentication — no username/password needed.
    Designed to run from an EC2 instance with an IAM role that has Neptune access.
    """

    def __init__(self, endpoint: str = None, port: int = None, region: str = None):
        self.endpoint = endpoint or NEPTUNE_ENDPOINT
        self.port = port or NEPTUNE_PORT
        self.region = region or AWS_REGION
        self.base_url = f"https://{self.endpoint}:{self.port}"
        self.opencypher_url = f"{self.base_url}/openCypher"

        # Get AWS credentials for SigV4 signing
        self._session = boto3.Session(region_name=self.region)
        self._refresh_auth()

        logger.info(f"NeptuneClient initialized: {self.endpoint}:{self.port} ({self.region})")

    def _refresh_auth(self):
        """Refresh AWS credentials (handles credential rotation)."""
        credentials = self._session.get_credentials().get_frozen_credentials()
        self._auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            self.region,
            "neptune-db",
            session_token=credentials.token,
        )

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
        # Build request body
        body = {"query": query}
        if parameters:
            body["parameters"] = json.dumps(parameters)

        for attempt in range(max_retries):
            try:
                # Refresh auth in case credentials rotated
                if attempt > 0:
                    self._refresh_auth()

                response = requests.post(
                    self.opencypher_url,
                    data=urlencode(body),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    auth=self._auth,
                    verify=True,
                )

                # Handle HTTP errors
                if response.status_code == 200:
                    result = response.json()
                    return result.get("results", [])

                elif response.status_code == 403:
                    logger.error(f"Access denied (403): Check IAM permissions. Response: {response.text[:200]}")
                    raise PermissionError(f"Neptune access denied: {response.text[:200]}")

                elif response.status_code == 400:
                    # Bad query syntax — don't retry
                    error_msg = response.text[:500]
                    logger.error(f"Query error (400): {error_msg}")
                    raise ValueError(f"Invalid openCypher query: {error_msg}")

                elif response.status_code in (429, 500, 503):
                    # Throttled or server error — retry
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries}: HTTP {response.status_code}, "
                        f"retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)

                else:
                    logger.error(f"Unexpected HTTP {response.status_code}: {response.text[:200]}")
                    raise RuntimeError(f"Neptune returned HTTP {response.status_code}")

            except requests.exceptions.ConnectionError as e:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries}: Connection error, "
                    f"retrying in {wait_time:.1f}s... ({e})"
                )
                time.sleep(wait_time)

            except (PermissionError, ValueError):
                # Don't retry auth or syntax errors
                raise

        logger.error(f"All {max_retries} attempts failed for query: {query[:100]}")
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
            query = f"MATCH (n:{label}) RETURN count(n) AS total"
        else:
            query = "MATCH (n) RETURN count(n) AS total"
        
        result = self.execute_query(query)
        return result[0]["total"] if result else 0

    def count_relationships(self, rel_type: str = None) -> int:
        """Count relationships in the graph, optionally filtered by type."""
        if rel_type:
            query = f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS total"
        else:
            query = "MATCH ()-[r]->() RETURN count(r) AS total"
        
        result = self.execute_query(query)
        return result[0]["total"] if result else 0

    def get_schema_summary(self) -> dict:
        """Get a summary of what's in the graph (node labels, relationship types, counts)."""
        # Get node labels and counts
        node_results = self.execute_query(
            "MATCH (n) RETURN labels(n) AS labels, count(n) AS count"
        )
        
        # Get relationship types and counts
        rel_results = self.execute_query(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count"
        )

        return {
            "nodes": node_results,
            "relationships": rel_results,
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
        print(f"   Nodes by label: {summary['nodes']}")
        print(f"   Relationships by type: {summary['relationships']}")

        print(f"\n✅ Neptune client working!")
    else:
        print(f"\n❌ Neptune is unhealthy: {health.get('error')}")
