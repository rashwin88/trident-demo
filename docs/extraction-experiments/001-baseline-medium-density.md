# Experiment 001 — Baseline Medium Density Extraction

**Date**: 2026-04-08
**Prompt version**: Pre-optimization (original `UnifiedExtractionSignature`)
**Density**: medium (5-10 entities, 2-5 concepts, 4-8 relationships, 4-8 propositions)
**Model**: OpenAI (via DSPy ChainOfThought)
**Document**: Synthetic technical doc — "Meridian Network Architecture" (4.7 KB, 3 chunks)

## Input Summary

A 6-section technical document describing a fictional distributed edge computing platform (Meridian) with:
- Named people (Dr. Sarah Chen, Dr. James Liu)
- Organizations (Axiom Systems Inc., Verizon, AT&T, Deloitte)
- Hardware (NVIDIA Jetson Orin NX, Xilinx Kria K26)
- Software services (Apache Kafka, Apache Flink, Apache Iceberg, Spark 3.5)
- Cloud services (AWS EKS, Amazon S3, DynamoDB, AWS KMS)
- Security (HashiCorp Vault, Cilium, SPIFFE)
- An operational procedure (ENRP — 6 steps)
- ML model (AnomalyNet v3.2 — TCN architecture)

## Results

| Metric | Value |
|--------|-------|
| Entities extracted | 30 |
| Concepts extracted | 14 |
| Relationships | 22 |
| Propositions | 24 |
| Entities merged (resolve) | 1 / 30 |
| Total duration | 126s |
| Extract duration | 94s |

## Entities (30)

| Label | Type | Notes |
|-------|------|-------|
| MEN | Device | Should be "Meridian Edge Node (MEN)" — duplicate |
| NOC | Organization | OK |
| ENRP | Procedure | OK |
| MCP | Service | Should be "Meridian Control Plane (MCP)" — duplicate |
| IPMI/BMC interface | Service | Wrong type — should be Interface |
| Jetson Orin module | Device | Should be "NVIDIA Jetson Orin NX" — duplicate |
| ServiceNow | Service | OK |
| meridian-cli | Service | OK — could be "Tool" |
| ICMP ping | Service | Wrong type — should be Protocol |
| SSH probe | Service | Wrong type — should be Protocol |
| Meridian | Service | OK — could be "Platform" |
| Axiom Systems Inc. | Organization | OK |
| Dr. Sarah Chen | Person | OK |
| Meridian Control Plane (MCP) | Service | OK |
| Meridian Edge Node (MEN) | Device | OK — duplicate of "MEN" |
| NVIDIA Jetson Orin NX | Device | OK — duplicate of "Jetson Orin module" |
| Meridian Model Registry (MMR) | Service | OK |
| Meridian Ingestion Gateway (MIG) | Service | OK |
| AWS EKS | Service | OK — could be "Platform" |
| Verizon | Organization | OK |
| Real-Time Inference Pipeline (RTIP) | Service | OK |
| Historical Analytics Pipeline (HAP) | Service | OK |
| AnomalyNet v3.2 | Service | Wrong type — should be Model |
| Meridian Edge Node (MEN) | Device | Exact duplicate (same chunk) |
| Meridian Incident Correlator (MIC) | Service | OK |
| Apache Kafka | Service | OK — could be "Framework" |
| Apache Flink | Service | OK — could be "Framework" |
| Axiom Data Governance Policy (DGP-2024-03) | Policy | OK |
| Telemetry Data | Data | OK |
| Internal — Carrier Confidential | Classification | OK |

## Missing Entities (not extracted)

- AT&T (Organization)
- Dr. James Liu (Person — CISO)
- Deloitte (Organization — auditor)
- HashiCorp Vault (Service/Platform)
- AWS KMS (Service)
- Cilium (Framework)
- Apache Iceberg (Framework)
- Amazon S3 (Service)
- DynamoDB (Database)
- Xilinx Kria K26 (Device — FPGA)
- Cisco NCS 5500 (Device — router)
- Juniper MX304 (Device — router)

## Issues Identified

### 1. Inconsistent entity labels (dedup failure)
- "MEN" vs "Meridian Edge Node (MEN)" — same entity, different labels across chunks
- "MCP" vs "Meridian Control Plane (MCP)"
- "Jetson Orin module" vs "NVIDIA Jetson Orin NX"
- Semantic resolver only caught 1 merge — threshold may be too high for abbreviation-vs-full-name pairs

### 2. Weak entity typing
The prompt only listed 6 example types: `Person, Organization, Location, Device, Circuit, Service`. The LLM shoehorned everything into "Service":
- AnomalyNet v3.2 → Service (should be Model)
- ICMP ping → Service (should be Protocol)
- SSH probe → Service (should be Protocol)
- IPMI/BMC interface → Service (should be Interface)
- Apache Kafka → Service (should be Framework)

### 3. Low entity recall at medium density
12+ entities missed entirely. The medium density prompt asked for only 5-10 entities per chunk, which is too conservative for information-dense technical documents.

### 4. Overuse of RELATED_TO
Several relationships used generic RELATED_TO where more specific edge types from the vocabulary would be appropriate:
- RTIP → MEN: `RELATED_TO` (should be `PROVISIONED_FROM` or similar)
- Meridian → Verizon: `RELATED_TO` (should be `PROVISIONED_FROM`)
- MCP → MEN: `RELATED_TO` (should be a control/orchestration edge)

### 5. Good results
- Concept extraction quality is strong — definitions are accurate and well-scoped
- Procedure entities (ENRP) correctly identified with IMPLEMENTED_BY and REFERENCES edges
- Propositions are grounded in the text
- The LLM discovered entity types not in the prompt (Policy, Data, Classification)

## Prompt Changes Applied

1. Added instruction to use full canonical names with acronyms
2. Expanded entity_type examples: added Model, Protocol, Interface, Framework, Platform, Policy, Standard, Database
3. Added "prefer specific edges over RELATED_TO" guidance
4. Added "extract ALL named entities — do not skip any"
5. Bumped medium density: 5-10 → 8-15 entities, 4-8 → 6-12 relationships
