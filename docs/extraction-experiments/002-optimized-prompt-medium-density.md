# Experiment 002 — Optimized Prompt, Medium Density

**Date**: 2026-04-08
**Prompt version**: Post-optimization (expanded entity types, canonical names, edge specificity)
**Density**: medium (8-15 entities, 3-6 concepts, 6-12 relationships, 5-10 propositions)
**Model**: OpenAI (via DSPy ChainOfThought)
**Document**: Same "Meridian Network Architecture" test doc as 001 (4.7 KB, 3 chunks)

## Results vs Baseline (Experiment 001)

| Metric | 001 (Baseline) | 002 (Optimized) | Delta |
|--------|---------------|-----------------|-------|
| Entities | 30 | 85 | +183% |
| Concepts | 14 | 14 | same |
| Relationships | 22 | 59 | +168% |
| Propositions | 24 | 36 | +50% |
| Entities merged | 1 / 30 | 7 / 85 | much better |
| Nodes stored | 85 | 146 | +72% |
| Edges stored | 181 | 395 | +118% |
| Extract time | 94s | 145s | +54% |
| Total time | 126s | 215s | +71% |

## Key Improvements

### 1. Entity typing — dramatically better
| Entity | 001 Type | 002 Type |
|--------|----------|----------|
| AnomalyNet v3.2 | Service | **Model** |
| ICMP ping | Service | **Protocol** (as "Internet Control Message Protocol (ICMP)") |
| SSH probe | Service | **Protocol** (as "Secure Shell (SSH)") |
| IPMI/BMC interface | Service | **Protocol** + **Device** (split into IPMI protocol + BMC device) |
| Apache Flink | Service | **Framework** |
| Apache Kafka | Service | **Platform** |
| MCP dashboard | (missing) | **Interface** |
| meridian-cli | Service | **Interface** (as "Meridian CLI (meridian-cli)") |

### 2. Previously missing entities — now extracted
All 12 missing entities from 001 are now captured:
- AT&T (Organization)
- Dr. James Liu (Person)
- Deloitte (Organization)
- HashiCorp Vault (Service)
- AWS KMS (Service)
- Cilium (Platform)
- Apache Iceberg (Platform)
- Amazon S3 (Service)
- Amazon DynamoDB (Service)
- Xilinx Kria K26 (Device)
- Cisco NCS 5500 (Device)
- Juniper MX304 (Device)

Plus many new ones the baseline missed entirely:
- Austin, Texas (Location)
- AWS Region us-east-1 (Location)
- JetPack 6.0 (Framework)
- Protocol Buffers (Standard)
- gRPC (Protocol)
- OAuth 2.0 (Protocol)
- JSON Web Token (JWT) (Standard)
- OpenAPI 3.1 (Standard)
- ONNX (Standard)
- TensorRT (Framework)
- BGP, MPLS, Segment Routing (Protocols)
- SOC 2 Type II (Standard)
- WebSocket Protocol (Protocol)
- SPIFFE (Standard)
- Kafka topics as named entities

### 3. Canonical naming — much improved
- 001: "MEN", "MCP", "ICMP ping", "SSH probe"
- 002: "Meridian Edge Node (MEN)", "Meridian Control Plane (MCP)", "Internet Control Message Protocol (ICMP)", "Secure Shell (SSH)"
- Resolver merged 7 entities (vs 1 in baseline) — canonical names help dedup

### 4. Relationship quality — more specific edges
- 001: Heavy use of `RELATED_TO`
- 002: Uses `PART_OF`, `CONTAINS`, `PROVISIONED_FROM`, `SOURCED_FROM`, `GOVERNED_BY`, `CLASSIFIED_AS`, `DESCRIBED_BY`, `TERMINATES_AT`, `IMPLEMENTED_BY` appropriately
- Example: `Meridian Edge Node (MEN) -[CONTAINS]-> NVIDIA Jetson Orin NX (8GB)` instead of generic RELATED_TO
- Example: `Real-Time Inference Pipeline (RTIP) -[TERMINATES_AT]-> Meridian Edge Node (MEN)` — correct use of domain edge
- Example: `Meridian Control Plane REST API -[DESCRIBED_BY]-> OpenAPI 3.1` — precise

### 5. Structural relationships captured
The optimized prompt correctly established the system hierarchy:
- `Meridian Control Plane (MCP) -[PART_OF]-> Meridian`
- `Meridian Edge Node (MEN) -[PART_OF]-> Meridian`
- `Meridian Model Registry (MMR) -[PART_OF]-> Meridian`
- `Meridian Ingestion Gateway (MIG) -[PART_OF]-> Meridian`
- `MCP dashboard -[PART_OF]-> Meridian Control Plane (MCP)`
- `Meridian Control Plane REST API -[PART_OF]-> Meridian Control Plane (MCP)`

## Remaining Issues

1. **Some RELATED_TO still used**: `Axiom Systems Inc. -[RELATED_TO]-> Austin, Texas` should be a location edge. `Meridian -[RELATED_TO]-> Verizon` could be `PROVISIONED_FROM`.
2. **"Jetson Orin module"** in chunk 3 still doesn't match "NVIDIA Jetson Orin NX (8GB)" in chunk 1 — but the resolver merged it (7 merges total).
3. **Over-extraction**: 85 entities is aggressive — some marginal items like "256GB NVMe storage" and "10GbE Uplink" as separate Device entities could be debated, but recall > precision is usually preferable for a knowledge graph.
4. **Extraction time increased** by ~50s — expected since more entities means more LLM output tokens.
5. **"Axiom Systems" vs "Axiom Systems Inc."** — slight label inconsistency across chunks, but resolver should merge these.

## Prompt Changes That Drove Improvement

1. **Canonical names**: "Use the FULL canonical name as the entity label" — eliminated most abbreviation-only labels
2. **Expanded type list**: Adding Model, Protocol, Interface, Framework, Platform, Policy, Standard, Database — LLM no longer shoehorns into Service
3. **Edge specificity**: "Prefer specific edges over RELATED_TO" — RELATED_TO usage dropped from ~30% to ~5% of edges
4. **Completeness instruction**: "Extract ALL named entities — do not skip any" + bumped density range — entity count nearly tripled
5. **Density bump**: 5-10 → 8-15 entities per chunk — each chunk now averages ~28 entities vs ~10 before

## Verdict

The prompt optimizations are a clear win across every dimension. Entity recall tripled, typing accuracy improved dramatically, relationship quality is much more specific, and the resolver is merging more effectively thanks to canonical naming. The cost is ~50% more extraction time, which is acceptable for the quality improvement.
