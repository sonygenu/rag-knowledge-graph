# Engineering Sync - June 10, 2026

## Attendees
- Sony Genu (Sr. Manager)
- Alice Chen (Principal Engineer)
- Bob Martinez (Sr. SDE)
- Carol Zhang (SDE II)
- Dave Wilson (SDE I)

## Agenda

### 1. Sprint Review

**Completed this sprint:**
- [x] Neptune cluster setup and IAM configuration (Carol)
- [x] Document parser v1 with Docling integration (Dave)
- [x] Entity extraction prompt engineering (Bob)

**Carried over:**
- [ ] Vector embedding pipeline (Alice) - blocked on OpenSearch cluster approval
- [ ] Batch processing Lambda (Dave) - needs architecture review

### 2. Architecture Decision: Graph Schema

Alice proposed two approaches for the knowledge graph schema:

**Option A: Flat entity model**
- All entities as generic nodes with a `type` property
- Simple to implement, flexible
- Risk: queries become complex

**Option B: Labeled node model**
- Separate labels for Person, Service, Team, Document
- More structured, faster queries via label filtering
- Risk: schema changes require migration

**Decision:** Go with Option B. Carol will implement the schema in Neptune this week.

### 3. Dependencies

| Dependency | Team | Status | Blocker |
|-----------|------|--------|---------|
| OpenSearch cluster | Platform | Pending | Budget approval needed |
| Bedrock model access | AI/ML | Approved | Claude 3 Sonnet available |
| VPC peering | Networking | In progress | ETA: Jun 14 |

### 4. Action Items

- **Alice:** Write design doc for vector embedding pipeline by Jun 13
- **Bob:** Test entity extraction with 100 sample documents by Jun 12
- **Carol:** Implement Neptune schema (Option B) by Jun 14
- **Dave:** Add PDF support to document parser by Jun 13
- **Sony:** Get budget approval for OpenSearch cluster

### 5. Risks

1. OpenSearch approval may slip, blocking hybrid search
2. Neptune query latency needs benchmarking before production
3. Bedrock rate limits may throttle batch entity extraction

## Next Meeting
June 17, 2026 - same time
