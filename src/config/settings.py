"""
Application settings - loaded from environment variables.
Never hardcode secrets here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Neptune Configuration
NEPTUNE_ENDPOINT = os.getenv("NEPTUNE_ENDPOINT", "")
NEPTUNE_PORT = int(os.getenv("NEPTUNE_PORT", "8182"))
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Bedrock Configuration
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")

# Chunking Configuration
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

def get_neptune_url():
    """Get the full Neptune HTTPS endpoint URL."""
    return f"https://{NEPTUNE_ENDPOINT}:{NEPTUNE_PORT}"
