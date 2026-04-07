import json
import logging
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from models import (
    DocumentType,
    KnowledgeChunk,
    KnowledgeStoreEntry,
    PipelineEvent,
    PipelineStage,
    ProviderStatus,
    ProceduralStoreEntry,
)
from ingestion.parsers import parse_document
from ingestion.chunker import chunk_document
from ingestion.dspy_programs import FullExtractionPipeline
from ingestion.extractor import extract_from_chunk
from ingestion.resolver import EntityResolver
from llm.embeddings import get_embedding_provider
from stores.graph import GraphStore
from stores.graph_index import GraphNodeIndex
from stores.knowledge import KnowledgeStore
from stores.procedural import ProceduralStore

logger = logging.getLogger(__name__)


def _event(
    stage: PipelineStage, message: str, detail: dict | None = None
) -> PipelineEvent:
    return PipelineEvent(stage=stage, message=message, detail=detail)


async def run_pipeline(
    content: bytes,
    filename: str,
    doc_type: DocumentType,
    provider_id: str,
    graph: GraphStore,
    knowledge_store: KnowledgeStore,
    procedural_store: ProceduralStore,
    graph_node_index: GraphNodeIndex | None = None,
) -> AsyncGenerator[PipelineEvent, None]:
    """Five-stage ingestion pipeline yielding SSE events as it progresses."""

    extraction_pipeline = FullExtractionPipeline()
    resolver = EntityResolver(graph)
    embedder = get_embedding_provider()
    pipeline_start = time.time()
    stage_times: dict[str, float] = {}

    # Mark provider as ingesting
    await graph.update_provider(provider_id, status=ProviderStatus.INGESTING)

    # ── Stage 1: Parse ────────────────────────────────
    stage_start = time.time()
    try:
        parse_result = parse_document(content, filename, doc_type)
        stage_times["parse"] = round(time.time() - stage_start, 2)

        # Build rich detail payload
        text_preview = parse_result.text[:500] + ("..." if len(parse_result.text) > 500 else "")
        detail = {
            **parse_result.metadata,
            "text_length": len(parse_result.text),
            "text_preview": text_preview,
            "file_size_kb": round(len(content) / 1024, 1),
            "doc_type": doc_type.value,
            "duration_s": stage_times["parse"],
        }
        page_info = ""
        if "page_count" in parse_result.metadata:
            page_info = f", {parse_result.metadata['page_count']} pages"
        elif "row_count" in parse_result.metadata:
            page_info = f", {parse_result.metadata['row_count']} rows"

        yield _event(
            PipelineStage.PARSE,
            f"Parsed {filename} ({doc_type.value}{page_info})",
            detail,
        )
    except Exception as e:
        await graph.update_provider(provider_id, status=ProviderStatus.ERROR)
        yield _event(PipelineStage.ERROR, f"Parse failed: {e}")
        return

    # ── Stage 2: Chunk ────────────────────────────────
    stage_start = time.time()
    if doc_type == DocumentType.SOP:
        from uuid import uuid4
        sop_chunk = KnowledgeChunk(
            chunk_id=str(uuid4()),
            provider_id=provider_id,
            source_file=filename,
            doc_type=doc_type,
            text=parse_result.text,
            char_start=0,
            char_end=len(parse_result.text),
        )
        chunks = [sop_chunk]
        stage_times["chunk"] = round(time.time() - stage_start, 2)
        yield _event(
            PipelineStage.CHUNK,
            "SOP treated as single document (no chunking)",
            {
                "count": 1,
                "mode": "sop_full_text",
                "duration_s": stage_times["chunk"],
                "chunks": [{"index": 0, "chars": len(parse_result.text), "preview": parse_result.text[:200]}],
            },
        )
    else:
        try:
            chunks = chunk_document(parse_result, provider_id, filename)
            stage_times["chunk"] = round(time.time() - stage_start, 2)

            # Build chunk previews (first 8 chunks)
            chunk_previews = [
                {
                    "index": i,
                    "chars": c.char_end - c.char_start,
                    "preview": c.text[:150] + ("..." if len(c.text) > 150 else ""),
                }
                for i, c in enumerate(chunks[:8])
            ]
            avg_chars = round(sum(c.char_end - c.char_start for c in chunks) / len(chunks)) if chunks else 0

            yield _event(
                PipelineStage.CHUNK,
                f"Created {len(chunks)} chunks",
                {
                    "count": len(chunks),
                    "avg_chunk_chars": avg_chars,
                    "duration_s": stage_times["chunk"],
                    "chunks": chunk_previews,
                },
            )
        except Exception as e:
            await graph.update_provider(provider_id, status=ProviderStatus.ERROR)
            yield _event(PipelineStage.ERROR, f"Chunking failed: {e}")
            return

    if not chunks:
        yield _event(PipelineStage.DONE, "No chunks produced — empty document")
        return

    # ── Stage 3: Extract ──────────────────────────────
    stage_start = time.time()
    all_entities = []
    all_concepts = []
    all_relations = []
    all_propositions = []
    all_procedures = []
    all_table_semantics = []
    extract_warnings = 0

    if doc_type == DocumentType.SOP:
        try:
            proc_data = extraction_pipeline.extract_procedure(parse_result.text)
            if proc_data:
                from ingestion.extractor import _build_procedure
                procedure = _build_procedure(proc_data, chunks[0].chunk_id)
                if procedure:
                    all_procedures.append(procedure)
                    yield _event(
                        PipelineStage.EXTRACT,
                        f"Extracted procedure: {procedure.name} ({len(procedure.steps)} steps)",
                        {
                            "procedure_name": procedure.name,
                            "steps": len(procedure.steps),
                            "step_names": [s.description[:80] for s in procedure.steps[:10]],
                        },
                    )
        except Exception as e:
            extract_warnings += 1
            logger.warning(f"Procedure extraction failed: {e}")
            yield _event(
                PipelineStage.EXTRACT,
                f"Warning: procedure extraction failed: {e}",
                {"warning": True},
            )

        stage_times["extract"] = round(time.time() - stage_start, 2)
        yield _event(
            PipelineStage.EXTRACT,
            f"SOP extraction complete — {len(all_procedures)} procedure(s)",
            {
                "procedures": len(all_procedures),
                "warnings": extract_warnings,
                "duration_s": stage_times["extract"],
                "summary": True,
            },
        )

    elif doc_type == DocumentType.DDL:
        try:
            sem_data = extraction_pipeline.extract_db_semantics(parse_result.text)
            if sem_data:
                from ingestion.extractor import _build_table_semantic
                table_sem = _build_table_semantic(sem_data)
                if table_sem:
                    all_table_semantics.append(table_sem)
                    yield _event(
                        PipelineStage.EXTRACT,
                        f"Extracted table schema: {table_sem.table_name} ({len(table_sem.columns)} columns)",
                        {
                            "table_name": table_sem.table_name,
                            "columns": [c.column_name for c in table_sem.columns],
                        },
                    )
        except Exception as e:
            extract_warnings += 1
            logger.warning(f"DDL extraction failed: {e}")

        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            yield _event(
                PipelineStage.EXTRACT,
                f"Extracting chunk {i + 1}/{total_chunks}...",
                {"chunk_index": i, "total": total_chunks, "progress": True},
            )
            try:
                result = extract_from_chunk(chunk, extraction_pipeline)
                all_entities.extend(result.entities)
                all_concepts.extend(result.concepts)
                all_relations.extend(result.relations)
                all_propositions.extend(result.propositions)
                # Emit per-chunk extraction results
                yield _event(
                    PipelineStage.EXTRACT,
                    f"Chunk {i + 1}: {len(result.entities)} entities, {len(result.concepts)} concepts",
                    {
                        "chunk_index": i,
                        "chunk_result": True,
                        "new_entities": [{"label": e.label, "type": e.entity_type} for e in result.entities],
                        "new_concepts": [{"name": c.name} for c in result.concepts],
                        "new_relations": [{"src": r.source_label, "edge": r.edge_type, "tgt": r.target_label} for r in result.relations],
                        "running_totals": {
                            "entities": len(all_entities),
                            "concepts": len(all_concepts),
                            "relationships": len(all_relations),
                            "propositions": len(all_propositions),
                        },
                    },
                )
            except Exception as e:
                extract_warnings += 1
                logger.warning(f"Extraction failed for chunk {i}: {e}")
                yield _event(
                    PipelineStage.EXTRACT,
                    f"Warning: extraction failed for chunk {i + 1}: {e}",
                    {"chunk_index": i, "warning": True},
                )

        stage_times["extract"] = round(time.time() - stage_start, 2)
        yield _event(
            PipelineStage.EXTRACT,
            f"Extracted {len(all_entities)} entities, {len(all_concepts)} concepts, "
            f"{len(all_table_semantics)} table schema(s)",
            {
                "entities": len(all_entities),
                "concepts": len(all_concepts),
                "table_semantics": len(all_table_semantics),
                "warnings": extract_warnings,
                "duration_s": stage_times["extract"],
                "summary": True,
                "all_entities": [{"label": e.label, "type": e.entity_type} for e in all_entities],
                "all_concepts": [{"name": c.name, "definition": c.definition[:100]} for c in all_concepts],
            },
        )

    else:
        # Standard documents: full per-chunk extraction with live entity streaming
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            yield _event(
                PipelineStage.EXTRACT,
                f"Extracting chunk {i + 1}/{total_chunks}...",
                {"chunk_index": i, "total": total_chunks, "progress": True},
            )
            try:
                result = extract_from_chunk(chunk, extraction_pipeline)
                all_entities.extend(result.entities)
                all_concepts.extend(result.concepts)
                all_relations.extend(result.relations)
                all_propositions.extend(result.propositions)
                # Emit per-chunk extraction results (live ticker data)
                yield _event(
                    PipelineStage.EXTRACT,
                    f"Chunk {i + 1}: {len(result.entities)} entities, {len(result.concepts)} concepts, {len(result.relations)} relationships",
                    {
                        "chunk_index": i,
                        "chunk_result": True,
                        "new_entities": [{"label": e.label, "type": e.entity_type} for e in result.entities],
                        "new_concepts": [{"name": c.name} for c in result.concepts],
                        "new_relations": [{"src": r.source_label, "edge": r.edge_type, "tgt": r.target_label} for r in result.relations],
                        "running_totals": {
                            "entities": len(all_entities),
                            "concepts": len(all_concepts),
                            "relationships": len(all_relations),
                            "propositions": len(all_propositions),
                        },
                    },
                )
            except Exception as e:
                extract_warnings += 1
                logger.warning(f"Extraction failed for chunk {i}: {e}")
                yield _event(
                    PipelineStage.EXTRACT,
                    f"Warning: extraction failed for chunk {i + 1}: {e}",
                    {"chunk_index": i, "warning": True},
                )

        stage_times["extract"] = round(time.time() - stage_start, 2)
        yield _event(
            PipelineStage.EXTRACT,
            f"Extracted {len(all_entities)} entities, {len(all_concepts)} concepts, "
            f"{len(all_relations)} relationships, {len(all_propositions)} propositions",
            {
                "entities": len(all_entities),
                "concepts": len(all_concepts),
                "relationships": len(all_relations),
                "propositions": len(all_propositions),
                "warnings": extract_warnings,
                "duration_s": stage_times["extract"],
                "summary": True,
                "all_entities": [{"label": e.label, "type": e.entity_type} for e in all_entities],
                "all_concepts": [{"name": c.name, "definition": c.definition[:100]} for c in all_concepts],
            },
        )

    # ── Stage 4: Resolve ──────────────────────────────
    stage_start = time.time()
    try:
        total, merged = await resolver.resolve_batch(all_entities, provider_id)
        new_count = total - merged
        stage_times["resolve"] = round(time.time() - stage_start, 2)
        yield _event(
            PipelineStage.RESOLVE,
            f"Resolved {total} entities, {new_count} new, {merged} merged",
            {
                "total": total,
                "new": new_count,
                "merged": merged,
                "duration_s": stage_times["resolve"],
                "entity_count_before": len(all_entities),
                "entity_count_after": new_count,
            },
        )
    except Exception as e:
        await graph.update_provider(provider_id, status=ProviderStatus.ERROR)
        yield _event(PipelineStage.ERROR, f"Resolution failed: {e}")
        return

    # ── Stage 5: Store ────────────────────────────────
    stage_start = time.time()
    try:
        node_count = 0
        edge_count = 0

        # 5a. Create Document node
        await graph.create_document_node(
            filename, doc_type.value, len(chunks), provider_id
        )
        node_count += 1

        # 5b. Create Chunk nodes + CONTAINS edges
        for chunk in chunks:
            await graph.create_chunk_node(chunk)
            node_count += 1
            edge_count += 1

        yield _event(
            PipelineStage.STORE,
            f"Stored document + {len(chunks)} chunk nodes",
            {"store_step": "chunks", "nodes": node_count, "edges": edge_count},
        )

        # 5c. Concepts → graph
        for concept in all_concepts:
            await graph.merge_concept(concept, provider_id)
            node_count += 1

        # 5d. Chunk → Entity edges (MENTIONS)
        for chunk in chunks:
            for entity in all_entities:
                await graph.create_chunk_entity_edge(
                    chunk.chunk_id, entity.label, provider_id
                )
                edge_count += 1

        # 5e. Chunk → Concept edges (DEFINES)
        for chunk in chunks:
            for concept in all_concepts:
                await graph.create_chunk_concept_edge(
                    chunk.chunk_id, concept.name, provider_id
                )
                edge_count += 1

        yield _event(
            PipelineStage.STORE,
            f"Created entity/concept edges ({edge_count} total)",
            {"store_step": "edges", "nodes": node_count, "edges": edge_count},
        )

        # 5f. Propositions → graph
        for prop in all_propositions:
            prop_node_id = await graph.create_proposition_node(prop, provider_id)
            node_count += 1
            await graph.create_chunk_proposition_edge(
                prop.chunk_id, prop_node_id, provider_id
            )
            edge_count += 1

        # 5g. Relationships → graph edges
        for rel in all_relations:
            await graph.create_edge(
                rel.source_label, rel.edge_type, rel.target_label, provider_id
            )
            edge_count += 1

        # 5h. Procedures → DAG in graph + Procedural Store
        for proc in all_procedures:
            step_ids = await graph.create_procedure_dag(proc, provider_id)
            node_count += 1 + len(step_ids)
            edge_count += len(step_ids)
            edge_count += max(0, len(step_ids) - 1)

            for step in proc.steps:
                if step.step_number in step_ids:
                    try:
                        step_entities = extraction_pipeline.extract_entities(step.description)
                        for ent_data in step_entities:
                            ent_label = ent_data.get("label", "")
                            if ent_label:
                                from models import ExtractedNamedEntity
                                ent = ExtractedNamedEntity(
                                    label=ent_label,
                                    entity_type=ent_data.get("entity_type", "Unknown"),
                                    description=ent_data.get("description"),
                                )
                                await graph.merge_entity(ent, provider_id)
                                await graph.link_step_to_entity(
                                    step_ids[step.step_number], ent_label, provider_id
                                )
                                edge_count += 1
                    except Exception as e:
                        logger.warning(f"Step entity extraction failed for step {step.step_number}: {e}")

            intent_embedding = embedder.embed(proc.intent)
            ps_entry = ProceduralStoreEntry(
                provider_id=provider_id,
                name=proc.name,
                intent=proc.intent,
                steps_json=json.dumps([s.model_dump() for s in proc.steps]),
                embedding=intent_embedding,
            )
            procedural_store.upsert_procedure(ps_entry, provider_id)

        # 5i. Table semantics → graph
        for ts in all_table_semantics:
            await graph.create_table_schema_node(ts, provider_id)
            node_count += 1

        # 5j. Knowledge Store — embed and upsert all chunks
        yield _event(
            PipelineStage.STORE,
            "Embedding chunks for vector store...",
            {"store_step": "embedding", "nodes": node_count, "edges": edge_count},
        )

        chunk_texts = [c.text for c in chunks]
        embeddings = embedder.embed_batch(chunk_texts)

        ks_entries = [
            KnowledgeStoreEntry(
                chunk_id=chunk.chunk_id,
                provider_id=provider_id,
                source_file=filename,
                doc_type=doc_type.value,
                text=chunk.text,
                embedding=emb,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )
            for chunk, emb in zip(chunks, embeddings)
        ]
        knowledge_store.upsert_chunks(ks_entries, provider_id)

        # 5k. Graph Node Index
        if graph_node_index:
            index_nodes = []
            for ent in all_entities:
                text = f"{ent.label}: {ent.description}" if ent.description else ent.label
                index_nodes.append({
                    "node_key": f"entity:{ent.label}",
                    "node_type": "Entity",
                    "text": text,
                })
            for concept in all_concepts:
                text = f"{concept.name}: {concept.definition}"
                index_nodes.append({
                    "node_key": f"concept:{concept.name}",
                    "node_type": "Concept",
                    "text": text,
                })
            for proc in all_procedures:
                text = f"{proc.name}: {proc.intent}"
                index_nodes.append({
                    "node_key": f"procedure:{proc.name}",
                    "node_type": "Procedure",
                    "text": text,
                })
                for step in proc.steps:
                    index_nodes.append({
                        "node_key": f"step:{proc.name}:{step.step_number}",
                        "node_type": "Step",
                        "text": step.description,
                    })
            indexed = graph_node_index.index_nodes_batch(provider_id, index_nodes)
            logger.info(f"Indexed {indexed} graph nodes for semantic search")

        stage_times["store"] = round(time.time() - stage_start, 2)
        total_duration = round(time.time() - pipeline_start, 2)

        yield _event(
            PipelineStage.STORE,
            f"Stored {node_count} nodes, {edge_count} edges, {len(chunks)} chunks",
            {
                "store_step": "complete",
                "nodes": node_count,
                "edges": edge_count,
                "chunks": len(chunks),
                "procedures": len(all_procedures),
                "duration_s": stage_times["store"],
                "summary": True,
            },
        )

    except Exception as e:
        await graph.update_provider(provider_id, status=ProviderStatus.ERROR)
        yield _event(PipelineStage.ERROR, f"Store failed: {e}")
        return

    # Update provider stats after successful ingestion
    try:
        live_stats = await graph.get_provider_stats(provider_id)
        await graph.update_provider(
            provider_id,
            status=ProviderStatus.READY,
            doc_count=(await graph.get_provider(provider_id)).doc_count + 1,
            node_count=live_stats.get("nodes", 0),
            chunk_count=live_stats.get("chunks", 0),
            edge_count=live_stats.get("nodes", 0),
            last_ingested_at=datetime.now(tz=UTC),
        )
    except Exception as e:
        logger.warning(f"Failed to update provider stats: {e}")

    total_duration = round(time.time() - pipeline_start, 2)
    yield _event(
        PipelineStage.DONE,
        "Ingestion complete",
        {
            "total_duration_s": total_duration,
            "stage_times": stage_times,
            "totals": {
                "nodes": node_count,
                "edges": edge_count,
                "chunks": len(chunks),
                "entities": len(all_entities),
                "concepts": len(all_concepts),
                "relationships": len(all_relations),
                "propositions": len(all_propositions),
                "procedures": len(all_procedures),
            },
        },
    )
