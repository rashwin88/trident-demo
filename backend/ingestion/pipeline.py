import json
import logging
from collections.abc import AsyncGenerator

from models import (
    DocumentType,
    KnowledgeChunk,
    KnowledgeStoreEntry,
    PipelineEvent,
    PipelineStage,
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

    # ── Stage 1: Parse ────────────────────────────────
    try:
        parse_result = parse_document(content, filename, doc_type)
        page_info = ""
        if "page_count" in parse_result.metadata:
            page_info = f", {parse_result.metadata['page_count']} pages"
        elif "row_count" in parse_result.metadata:
            page_info = f", {parse_result.metadata['row_count']} rows"
        yield _event(
            PipelineStage.PARSE,
            f"Parsed {filename} ({doc_type.value}{page_info})",
            parse_result.metadata,
        )
    except Exception as e:
        yield _event(PipelineStage.ERROR, f"Parse failed: {e}")
        return

    # ── Stage 2: Chunk ────────────────────────────────
    # SOPs are treated as a single unit — no chunking, just one KS entry for search
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
        yield _event(
            PipelineStage.CHUNK,
            "SOP treated as single document (no chunking)",
            {"count": 1, "mode": "sop_full_text"},
        )
    else:
        try:
            chunks = chunk_document(parse_result, provider_id, filename)
            yield _event(
                PipelineStage.CHUNK,
                f"Created {len(chunks)} chunks",
                {"count": len(chunks)},
            )
        except Exception as e:
            yield _event(PipelineStage.ERROR, f"Chunking failed: {e}")
            return

    if not chunks:
        yield _event(PipelineStage.DONE, "No chunks produced — empty document")
        return

    # ── Stage 3: Extract ──────────────────────────────
    all_entities = []
    all_concepts = []
    all_relations = []
    all_propositions = []
    all_procedures = []
    all_table_semantics = []
    extract_warnings = 0

    if doc_type == DocumentType.SOP:
        # SOP: extract procedure from full text only — no per-chunk LLM calls
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
                        {"procedure_name": procedure.name, "steps": len(procedure.steps)},
                    )
        except Exception as e:
            extract_warnings += 1
            logger.warning(f"Procedure extraction failed: {e}")
            yield _event(
                PipelineStage.EXTRACT,
                f"Warning: procedure extraction failed: {e}",
                {"warning": True},
            )

        detail = {
            "procedures": len(all_procedures),
            "warnings": extract_warnings,
        }
        yield _event(
            PipelineStage.EXTRACT,
            f"SOP extraction complete — {len(all_procedures)} procedure(s)",
            detail,
        )

    elif doc_type == DocumentType.DDL:
        # DDL: extract table semantics from full text, then per-chunk for entities
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
                        {"table_name": table_sem.table_name},
                    )
        except Exception as e:
            extract_warnings += 1
            logger.warning(f"DDL extraction failed: {e}")

        # Also do per-chunk extraction for entities/concepts
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
            except Exception as e:
                extract_warnings += 1
                logger.warning(f"Extraction failed for chunk {i}: {e}")
                yield _event(
                    PipelineStage.EXTRACT,
                    f"Warning: extraction failed for chunk {i + 1}: {e}",
                    {"chunk_index": i, "warning": True},
                )

        detail = {
            "entities": len(all_entities),
            "concepts": len(all_concepts),
            "table_semantics": len(all_table_semantics),
            "warnings": extract_warnings,
        }
        yield _event(
            PipelineStage.EXTRACT,
            f"Extracted {len(all_entities)} entities, {len(all_concepts)} concepts, "
            f"{len(all_table_semantics)} table schema(s)",
            detail,
        )

    else:
        # Standard documents (PDF, TEXT, CSV): full per-chunk extraction
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
            except Exception as e:
                extract_warnings += 1
                logger.warning(f"Extraction failed for chunk {i}: {e}")
                yield _event(
                    PipelineStage.EXTRACT,
                    f"Warning: extraction failed for chunk {i + 1}: {e}",
                    {"chunk_index": i, "warning": True},
                )

        detail = {
            "entities": len(all_entities),
            "concepts": len(all_concepts),
            "relationships": len(all_relations),
            "propositions": len(all_propositions),
            "warnings": extract_warnings,
        }
        yield _event(
            PipelineStage.EXTRACT,
            f"Extracted {len(all_entities)} entities, {len(all_concepts)} concepts, "
            f"{len(all_relations)} relationships, {len(all_propositions)} propositions",
            detail,
        )

    # ── Stage 4: Resolve ──────────────────────────────
    try:
        total, merged = await resolver.resolve_batch(all_entities, provider_id)
        new_count = total - merged
        yield _event(
            PipelineStage.RESOLVE,
            f"Resolved {total} entities, {new_count} new, {merged} merged",
            {"total": total, "new": new_count, "merged": merged},
        )
    except Exception as e:
        yield _event(PipelineStage.ERROR, f"Resolution failed: {e}")
        return

    # ── Stage 5: Store ────────────────────────────────
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
            edge_count += 1  # CONTAINS

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

        # 5f. Propositions → graph
        for prop in all_propositions:
            prop_node_id = await graph.create_proposition_node(prop, provider_id)
            node_count += 1
            # ASSERTS edge from chunk
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
            # Create Procedure + Step nodes as DAG with PRECEDES edges
            step_ids = await graph.create_procedure_dag(proc, provider_id)
            node_count += 1 + len(step_ids)  # procedure + steps
            edge_count += len(step_ids)  # HAS_STEP edges
            edge_count += max(0, len(step_ids) - 1)  # PRECEDES edges (approx)

            # Extract entities per step and link to existing Entity nodes
            for step in proc.steps:
                if step.step_number in step_ids:
                    try:
                        step_entities = extraction_pipeline.extract_entities(step.description)
                        for ent_data in step_entities:
                            ent_label = ent_data.get("label", "")
                            if ent_label:
                                # Merge entity if new, then link step → entity
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

            # Procedural Store entry
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

        # 5k. Graph Node Index — semantic index over entities/concepts/procedures
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

        yield _event(
            PipelineStage.STORE,
            f"Stored {node_count} nodes, {edge_count} edges, {len(chunks)} chunks",
            {
                "nodes": node_count,
                "edges": edge_count,
                "chunks": len(chunks),
                "procedures": len(all_procedures),
            },
        )

    except Exception as e:
        yield _event(PipelineStage.ERROR, f"Store failed: {e}")
        return

    yield _event(PipelineStage.DONE, "Ingestion complete")
