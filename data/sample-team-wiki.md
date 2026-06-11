# AWS RAG Ingestion Team

## Team Overview

The RAG Ingestion team builds scalable document ingestion pipelines that power Amazon Q Business, AWS Managed Knowledge Base, and Quick Suite. We handle document parsing, entity extraction, and knowledge graph construction at enterprise scale.

## Team Members

| Name | Role | Focus Area |
|------|------|-----------|
| Sony Genu | Sr. Manager | Team leadership, AI strategy |
| Alice Chen | Principal Engineer | Pipeline architecture |
| Bob Martinez | Sr. SDE | Entity extraction, NLP |
| Carol Zhang | SDE II | Graph database, Neptune |
| Dave Wilson | SDE I | Document parsing, Docling |

## Services We Own

### Plato Ingestion Service
- **Type:** Microservice
- **Language:** Python, Java
- **Dependencies:** S3, SQS, Bedrock, Neptune
- **On-call rotation:** Weekly, starting Monday

### Document Parser Service
- **Type:** Lambda function
- **Language:** Python
- **Dependencies:** Docling, S3, Step Functions
- **Throughput:** 10,000 documents/hour

## Architecture

The ingestion pipeline follows this flow:

1. Documents uploaded to S3 (PDF, DOCX, HTML)
2. S3 event triggers Step Functions workflow
3. Document Parser Service extracts text and structure
4. Entity Extraction Service identifies entities and relationships
5. Knowledge Graph Loader writes to Neptune
6. Vector embeddings stored in OpenSearch

## Runbooks

### High Latency Alert
- Check CloudWatch metrics for the Plato Ingestion Service
- Verify SQS queue depth is not spiking
- Check Neptune cluster CPU utilization
- Contact Carol Zhang if Neptune-related

### Failed Document Processing
- Check Step Functions execution history
- Look for parsing errors in CloudWatch Logs
- Retry failed documents via the admin console
- Contact Dave Wilson for parsing issues

## Quarterly Goals (Q3 2026)

1. Reduce document processing latency by 40%
2. Add support for multi-modal documents (images + text)
3. Implement incremental knowledge graph updates
4. Launch self-service document upload for internal teams
