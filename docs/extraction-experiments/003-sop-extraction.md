# Experiment 003 — SOP Extraction

**Date**: 2026-04-08  
**Document**: Synthetic SOP — "Database Failover and Recovery" (5.7 KB, 10 steps)  
**doc_type**: sop  
**Density**: medium

## Input Summary

A detailed database failover SOP with:
- Named services: Aurora PostgreSQL, AWS RDS, CloudWatch, PagerDuty, Route53, HikariCP, Grafana, Tailscale
- Named people: Rajesh Krishnamurthy (VP Infrastructure)
- Teams: DRE, SRE, Platform Engineering
- Infrastructure: bastion host, prod-aurora-pg-01, specific IAM roles
- 10 procedure steps with prerequisites and rollback instructions

## Results (Pre-Fix)

| Metric | Value |
|--------|-------|
| Procedure extracted | 1 (11 steps — extra step from rollback section) |
| Entities | **0** |
| Concepts | **0** |
| Relationships | **0** |
| Propositions | **0** |

### Bug Found

The SOP extraction path (`doc_type == DocumentType.SOP`) only called `extract_procedure()` for step structure. It **never called `extract_unified()`** to capture entities, concepts, and relationships from the SOP text. All named services, people, teams, and infrastructure in the document were completely lost.

The procedure DAG was created (Procedure → Steps with HAS_STEP/PRECEDES edges), but the steps had no REFERENCES edges to any entities because no entities existed.

### Fix Applied

Added a second extraction call in the SOP path: after `extract_procedure()`, also run `extract_from_chunk()` on the SOP text to capture entities/concepts/relationships. These get stored in the graph and linked to the chunk via scoped MENTIONS/DEFINES edges (R1 fix).

**File changed**: `backend/ingestion/pipeline.py` — SOP extraction branch now runs both procedure extraction and unified entity extraction.

## Expected Results (Post-Fix)

After restart, the same SOP should produce:
- 1 procedure with ~10 steps (unchanged)
- 15-30 entities (Aurora PostgreSQL, AWS RDS, CloudWatch, PagerDuty, etc.)
- 5-10 concepts (failover, replication lag, automated failover, etc.)
- 10-20 relationships (step REFERENCES entity, service PART_OF platform, etc.)
- Step nodes should get REFERENCES edges to extracted entities

## Verdict

Critical gap in the SOP pipeline — procedure structure was extracted but no knowledge graph content. Fix adds one additional LLM call per SOP ingestion.
