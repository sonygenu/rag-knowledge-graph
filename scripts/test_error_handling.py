"""
Test Error Handling for Entity Extraction.

Simulates various error scenarios to verify retry logic works correctly.

Run on bastion:
    cd ~/rag-knowledge-graph
    python3 scripts/test_error_handling.py
"""
import json
import logging
import sys
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

# Setup logging to see all retry behavior
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

sys.path.insert(0, ".")
from src.extract.entity_extractor import _call_bedrock_with_retry, extract_from_chunk
from src.ingest.chunker import Chunk

# Test chunk for extraction
TEST_CHUNK = Chunk(
    content="Alice Chen is a Principal Engineer who owns the Plato Ingestion Service.",
    metadata={"section": "Test Section", "source": "test.md"}
)

TEST_SCHEMA = {
    "entity_types": [
        {"name": "Person", "description": "A human"},
        {"name": "Service", "description": "A software service"},
    ],
    "relationship_types": [
        {"name": "OWNS", "from_type": "Person", "to_type": "Service", "description": "Ownership"},
    ]
}

VALID_JSON_RESPONSE = json.dumps({
    "entities": [
        {"name": "Alice Chen", "type": "Person", "properties": {"role": "Principal Engineer"}},
        {"name": "Plato Ingestion Service", "type": "Service", "properties": {}}
    ],
    "relationships": [
        {"from": "Alice Chen", "to": "Plato Ingestion Service", "type": "OWNS", "properties": {}}
    ]
})


def make_client_error(code, message="Test error"):
    """Helper to create a boto3 ClientError."""
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        "InvokeModel"
    )


def make_success_response(text):
    """Helper to create a successful Bedrock response."""
    mock_response = MagicMock()
    mock_response.__getitem__ = lambda self, key: {
        "body": MagicMock(read=lambda: json.dumps({"content": [{"text": text}]}).encode())
    }[key]
    return mock_response


print("=" * 60)
print("ERROR HANDLING TEST SUITE")
print("=" * 60)

results = []

# --- Test 1: ThrottlingException with retry ---
print("\n\n🧪 TEST 1: ThrottlingException (should retry 3 times with backoff)")
print("-" * 60)

with patch("src.extract.entity_extractor.boto3") as mock_boto3:
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_client.invoke_model.side_effect = make_client_error("ThrottlingException", "Rate exceeded")

    result = _call_bedrock_with_retry("test prompt", "test-model", max_retries=3)
    
    call_count = mock_client.invoke_model.call_count
    print(f"  Result: {result}")
    print(f"  Invoke attempts: {call_count}")
    print(f"  ✓ Correctly retried {call_count} times then returned None")
    results.append(("ThrottlingException", "PASS" if result is None and call_count == 3 else "FAIL"))


# --- Test 2: AccessDeniedException (no retry) ---
print("\n\n🧪 TEST 2: AccessDeniedException (should NOT retry — fail immediately)")
print("-" * 60)

with patch("src.extract.entity_extractor.boto3") as mock_boto3:
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_client.invoke_model.side_effect = make_client_error("AccessDeniedException", "No access")

    result = _call_bedrock_with_retry("test prompt", "test-model", max_retries=3)
    
    call_count = mock_client.invoke_model.call_count
    print(f"  Result: {result}")
    print(f"  Invoke attempts: {call_count}")
    print(f"  ✓ Correctly failed immediately (1 attempt, no retry)")
    results.append(("AccessDeniedException", "PASS" if result is None and call_count == 1 else "FAIL"))


# --- Test 3: ValidationException (no retry) ---
print("\n\n🧪 TEST 3: ValidationException (should NOT retry — config problem)")
print("-" * 60)

with patch("src.extract.entity_extractor.boto3") as mock_boto3:
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_client.invoke_model.side_effect = make_client_error("ValidationException", "Invalid model")

    result = _call_bedrock_with_retry("test prompt", "test-model", max_retries=3)
    
    call_count = mock_client.invoke_model.call_count
    print(f"  Result: {result}")
    print(f"  Invoke attempts: {call_count}")
    print(f"  ✓ Correctly failed immediately (1 attempt, no retry)")
    results.append(("ValidationException", "PASS" if result is None and call_count == 1 else "FAIL"))


# --- Test 4: ServiceUnavailableException with retry ---
print("\n\n🧪 TEST 4: ServiceUnavailableException (should retry with backoff)")
print("-" * 60)

with patch("src.extract.entity_extractor.boto3") as mock_boto3:
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_client.invoke_model.side_effect = make_client_error("ServiceUnavailableException", "Service down")

    result = _call_bedrock_with_retry("test prompt", "test-model", max_retries=2)
    
    call_count = mock_client.invoke_model.call_count
    print(f"  Result: {result}")
    print(f"  Invoke attempts: {call_count}")
    print(f"  ✓ Correctly retried {call_count} times then returned None")
    results.append(("ServiceUnavailableException", "PASS" if result is None and call_count == 2 else "FAIL"))


# --- Test 5: Success on first try ---
print("\n\n🧪 TEST 5: Successful response (should return immediately)")
print("-" * 60)

with patch("src.extract.entity_extractor.boto3") as mock_boto3:
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps({"content": [{"text": VALID_JSON_RESPONSE}]}).encode()
    mock_client.invoke_model.return_value = {"body": mock_body}

    result = _call_bedrock_with_retry("test prompt", "test-model", max_retries=3)
    
    call_count = mock_client.invoke_model.call_count
    print(f"  Result: {result[:80]}...")
    print(f"  Invoke attempts: {call_count}")
    print(f"  ✓ Correctly returned on first attempt")
    results.append(("Success", "PASS" if result is not None and call_count == 1 else "FAIL"))


# --- Test 6: Throttle then success (retry recovers) ---
print("\n\n🧪 TEST 6: Throttle on 1st attempt, success on 2nd (retry recovers)")
print("-" * 60)

with patch("src.extract.entity_extractor.boto3") as mock_boto3:
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps({"content": [{"text": VALID_JSON_RESPONSE}]}).encode()
    
    mock_client.invoke_model.side_effect = [
        make_client_error("ThrottlingException", "Rate exceeded"),
        {"body": mock_body},
    ]

    result = _call_bedrock_with_retry("test prompt", "test-model", max_retries=3)
    
    call_count = mock_client.invoke_model.call_count
    print(f"  Result: {result[:80] if result else None}...")
    print(f"  Invoke attempts: {call_count}")
    print(f"  ✓ Correctly retried after throttle and succeeded on 2nd attempt")
    results.append(("Throttle→Success", "PASS" if result is not None and call_count == 2 else "FAIL"))


# --- Test 7: Malformed JSON response (retry) ---
print("\n\n🧪 TEST 7: Malformed JSON response (should retry)")
print("-" * 60)

with patch("src.extract.entity_extractor.boto3") as mock_boto3:
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    
    # First call returns non-JSON, second returns valid JSON
    mock_body_bad = MagicMock()
    mock_body_bad.read.return_value = json.dumps({"content": [{"text": "I cannot extract entities from this text."}]}).encode()
    
    mock_body_good = MagicMock()
    mock_body_good.read.return_value = json.dumps({"content": [{"text": VALID_JSON_RESPONSE}]}).encode()
    
    mock_client.invoke_model.side_effect = [
        {"body": mock_body_bad},
        {"body": mock_body_good},
    ]

    result = _call_bedrock_with_retry("test prompt", "test-model", max_retries=3)
    
    call_count = mock_client.invoke_model.call_count
    print(f"  Result: {result[:80] if result else None}...")
    print(f"  Invoke attempts: {call_count}")
    print(f"  ✓ Correctly retried after malformed response and got valid JSON")
    results.append(("MalformedJSON→Success", "PASS" if result is not None and call_count == 2 else "FAIL"))


# --- Test 8: Full extract_from_chunk with failed Bedrock ---
print("\n\n🧪 TEST 8: extract_from_chunk with all retries failing (graceful degradation)")
print("-" * 60)

with patch("src.extract.entity_extractor.boto3") as mock_boto3:
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_client.invoke_model.side_effect = make_client_error("ThrottlingException", "Rate exceeded")

    result = extract_from_chunk(TEST_CHUNK, TEST_SCHEMA, model_id="test-model")
    
    print(f"  Result: {result}")
    print(f"  Entities: {len(result.entities)}")
    print(f"  Relationships: {len(result.relationships)}")
    print(f"  ✓ Correctly returned empty ExtractionResult (no crash)")
    results.append(("GracefulDegradation", "PASS" if len(result.entities) == 0 else "FAIL"))


# --- Summary ---
print("\n\n" + "=" * 60)
print("TEST RESULTS SUMMARY")
print("=" * 60)
for name, status in results:
    icon = "✅" if status == "PASS" else "❌"
    print(f"  {icon} {name}: {status}")

passed = sum(1 for _, s in results if s == "PASS")
total = len(results)
print(f"\n  {passed}/{total} tests passed")
print("=" * 60)
