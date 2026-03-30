# Ingestion Pipeline

The ingestion pipeline converts raw documents into structured knowledge across four stores. It uses **Docling** for document parsing and chunking, and **DSPy** for LLM-driven extraction.

## Pipeline Overview

```
     Upload                                                              Four Stores
    ┌──────┐     ┌───────┐     ┌───────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ File │────▶│ Parse │────▶│ Chunk │────▶│ Extract │────▶│ Resolve │────▶│  Store  │
    └──────┘     └───────┘     └───────┘     └─────────┘     └─────────┘     └─────────┘
                  Docling       Docling        DSPy           Neo4j          Neo4j
                  Document      Hybrid         ChainOf        fuzzy          + Milvus KS
                  Converter     Chunker        Thought        match          + Milvus PS
                               (or SOP                                      + Milvus GN
                                bypass)
```

## Stage 1 — Parse (Docling DocumentConverter)

Docling converts documents in **light mode** — no OCR, fast table structure detection.

| Document Type | Docling Path | Notes |
|---------------|-------------|-------|
| PDF | `converter.convert(file)` | No OCR, `TableFormerMode.FAST` |
| TEXT | `converter.convert_string(text, format=MD)` | Treated as Markdown |
| SOP | `converter.convert_string(text, format=MD)` | Same as TEXT, triggers procedure extraction downstream |
| CSV | `converter.convert(file)` | Native Docling CSV support |
| DDL | `converter.convert_string(text, format=MD)` | Triggers DB semantics extraction downstream |

Output: `ParseResult` containing the full text (as Markdown) and the `DoclingDocument` object.

```mermaid
sequenceDiagram
    participant R as Router
    participant P as parsers.py
    participant D as Docling

    R->>P: parse_document(content, filename, doc_type)
    alt PDF or CSV
        P->>D: converter.convert(temp_file)
    else TEXT / SOP / DDL
        P->>D: converter.convert_string(text, format=MD)
    end
    D-->>P: ConversionResult
    P->>P: Export to Markdown + build metadata
    P-->>R: ParseResult (text + DoclingDocument)
```

## Stage 2 — Chunk (Docling HybridChunker or SOP Bypass)

### Standard Documents (PDF, TEXT, CSV, DDL)

Uses Docling's `HybridChunker` for **structure-aware, token-aware** chunking:

- Starts from the document's hierarchical structure (headings, paragraphs, tables)
- Splits oversized elements, merges undersized adjacent peers
- Token counting via OpenAI's `cl100k_base` tokenizer
- `contextualize()` prepends heading context to each chunk for better embeddings

```mermaid
sequenceDiagram
    participant P as Pipeline
    participant C as chunker.py
    participant HC as HybridChunker

    P->>C: chunk_document(parse_result, provider_id, filename)
    C->>HC: chunker.chunk(docling_document)
    HC-->>C: docling_chunks[]
    loop Each chunk
        C->>HC: chunker.contextualize(chunk)
        HC-->>C: text with heading context
        C->>C: Build KnowledgeChunk
    end
    C-->>P: KnowledgeChunk[]
```

### SOP Documents — No Chunking

SOPs are treated as a single unit. The full parsed text becomes one `KnowledgeChunk`:

```mermaid
sequenceDiagram
    participant P as Pipeline

    P->>P: doc_type == SOP?
    P->>P: Create single KnowledgeChunk(text=full_text, char_start=0, char_end=len)
    P-->>P: [one_chunk]
    P-->>FE: SSE: {stage: chunk, detail: {count: 1, mode: "sop_full_text"}}
```

This ensures the full SOP context is available for procedure extraction in Stage 3.

### Why Docling over naive sliding window?

| Feature | Naive Sliding Window | Docling HybridChunker |
|---------|---------------------|----------------------|
| Respects headings | No — splits mid-sentence | Yes — heading context preserved |
| Table handling | Breaks tables across chunks | Keeps tables intact |
| Token-aware | No — character-based | Yes — uses tokenizer |
| Merge small sections | No | Yes — `merge_peers=True` |
| Heading context | Lost | Prepended via `contextualize()` |

A text fallback (`_chunk_text_fallback`) exists for cases where no `DoclingDocument` is available.

## Stage 3 — Extract (DSPy)

Extraction depends on the document type:

### Standard Documents (PDF, TEXT, CSV)

Four extraction modules run on each chunk. All use `dspy.ChainOfThought` for reasoning.

```mermaid
sequenceDiagram
    participant P as Pipeline
    participant E as FullExtractionPipeline
    participant LLM as LLM (via DSPy)

    loop Each chunk
        P->>E: extract_from_chunk(chunk)

        par Entity + Concept extraction
            E->>LLM: NamedEntitySignature(chunk_text)
            LLM-->>E: entities JSON
            E->>LLM: ConceptSignature(chunk_text)
            LLM-->>E: concepts JSON
        end

        E->>E: Parse entity labels for grounding

        E->>LLM: RelationshipSignature(chunk_text, labels, edges)
        LLM-->>E: relationships JSON

        E->>LLM: PropositionSignature(chunk_text)
        LLM-->>E: propositions JSON

        E-->>P: ExtractionResult
    end

    Note over P: Per-chunk progress events: SSE {chunk_index, total, progress: true}
```

### SOP Documents

No per-chunk extraction. The full text goes directly to `ProcedureSignature`:

```mermaid
sequenceDiagram
    participant P as Pipeline
    participant E as FullExtractionPipeline
    participant LLM as LLM (via DSPy)

    P->>E: extract_procedure(full_text)
    E->>LLM: ProcedureSignature(full_text)
    LLM-->>E: procedure JSON (name, intent, steps[])
    E-->>P: ExtractedProcedure
    P-->>FE: SSE: {stage: extract, detail: {procedure_name, steps}}
```

### DDL Documents

Table semantics are extracted first from the full text, then per-chunk extraction runs for entities/concepts.

### Extraction failure handling

- All DSPy outputs are JSON strings parsed with `try/except`
- On parse failure: log warning, return empty list — **never crash the pipeline**
- Failed chunks emit an SSE warning event to the frontend

## Stage 4 — Resolve (Entity Deduplication)

Case-insensitive string matching against existing entities in Neo4j.

```mermaid
sequenceDiagram
    participant P as Pipeline
    participant R as EntityResolver
    participant G as Neo4j

    loop Each extracted entity
        R->>R: Check local cache (provider:lower_label)
        alt Cache hit
            R-->>P: existing node_id, is_new=false
        else Cache miss
            R->>G: fuzzy_find_entities([label], provider_id)
            alt Match found
                G-->>R: existing node
                R->>R: Update cache
                R-->>P: existing node_id, is_new=false
            else No match
                R->>G: merge_entity(entity, provider_id)
                G-->>R: new node_id
                R->>R: Update cache
                R-->>P: new node_id, is_new=true
            end
        end
    end
```

## Stage 5 — Store

Writes all resolved objects into four stores in order:

1. **Neo4j**: Document → Chunk → Entity → Concept → Proposition nodes, plus all edges and relationships
2. **Neo4j (SOP DAG)**: Procedure → Step nodes with HAS_STEP, PRECEDES, and REFERENCES edges
3. **Milvus PS**: Embed procedure intents, upsert into `ps_{provider_id}` (SOP docs only)
4. **Milvus KS**: Embed chunk texts via embedding provider, upsert into `ks_{provider_id}`
5. **Milvus GN**: Embed entity/concept/procedure/step labels, upsert into `gn_{provider_id}`

```mermaid
sequenceDiagram
    participant P as Pipeline
    participant EMB as Embedding Provider
    participant G as Neo4j
    participant KS as Milvus KS
    participant PS as Milvus PS
    participant GN as Milvus GN

    P->>G: create_document_node + chunk nodes + edges
    P->>G: merge entities + concepts
    P->>G: create propositions + edges
    P->>G: create relationships (constrained vocabulary)

    opt Procedures extracted (SOP)
        P->>G: create_procedure_dag (Procedure + Step nodes + edges)
        loop Each step
            P->>G: extract entities from step description
            P->>G: link_step_to_entity (REFERENCES edges)
        end
        P->>EMB: embed(procedure.intent)
        P->>PS: upsert_procedure
    end

    opt Table semantics (DDL)
        P->>G: create_table_schema_node
    end

    P->>EMB: embed_batch(chunk_texts)
    P->>KS: upsert_chunks(entries)

    P->>EMB: embed_batch(entity/concept/procedure/step texts)
    P->>GN: index_nodes_batch(provider_id, nodes)

    P-->>FE: SSE: {stage: store}
    P-->>FE: SSE: {stage: done}
```

## SSE Event Stream

The pipeline emits `PipelineEvent` objects via an async generator. The frontend consumes them as Server-Sent Events.

| Stage | Example Message | Detail |
|-------|----------------|--------|
| `parse` | "Parsed contract.pdf (pdf, 12 pages)" | `{filename, page_count}` |
| `chunk` | "Created 24 chunks" | `{count: 24}` |
| `chunk` | "SOP treated as single document (no chunking)" | `{count: 1, mode: "sop_full_text"}` |
| `extract` | "Extracting chunk 3/24..." | `{chunk_index: 2, total: 24, progress: true}` |
| `extract` | "Extracted 15 entities, 3 concepts..." | `{entities, concepts, ...}` |
| `extract` | "Extracted procedure: Circuit Decommission (5 steps)" | `{procedure_name, steps}` |
| `extract` | "Warning: extraction failed for chunk 7" | `{chunk_index: 6, warning: true}` |
| `resolve` | "Resolved 15 entities, 12 new, 3 merged" | `{total, new, merged}` |
| `store` | "Stored 42 nodes, 38 edges, 24 chunks" | `{nodes, edges, chunks, procedures}` |
| `done` | "Ingestion complete" | — |
| `error` | "Parse failed: ..." | — |
