import logging

from models import (
    DocumentType,
    ExtractedConcept,
    ExtractedNamedEntity,
    ExtractedProposition,
    ExtractedProcedure,
    ExtractedRelationship,
    ExtractedTableSemantic,
    ExtractionResult,
    KnowledgeChunk,
    ColumnSemantic,
    ProcedureStep,
)
from ingestion.dspy_programs import FullExtractionPipeline

logger = logging.getLogger(__name__)


def extract_from_chunk(
    chunk: KnowledgeChunk,
    pipeline: FullExtractionPipeline,
) -> ExtractionResult:
    """Run all extraction modules on a single chunk and return typed models."""
    text = chunk.text

    # Extract entities
    entities = _build_entities(pipeline.extract_entities(text))

    # Extract concepts
    concepts = _build_concepts(pipeline.extract_concepts(text))

    # Extract relationships (grounded to extracted entity labels)
    entity_labels = [e.label for e in entities]
    relations = _build_relationships(
        pipeline.extract_relationships(text, entity_labels)
    )

    # Extract propositions
    propositions = _build_propositions(
        pipeline.extract_propositions(text), chunk.chunk_id
    )

    # Extract procedure (SOP only)
    procedure = None
    if chunk.doc_type == DocumentType.SOP:
        proc_data = pipeline.extract_procedure(text)
        procedure = _build_procedure(proc_data, chunk.chunk_id)

    # Extract table semantics (DDL only)
    table_semantic = None
    if chunk.doc_type == DocumentType.DDL:
        sem_data = pipeline.extract_db_semantics(text)
        table_semantic = _build_table_semantic(sem_data)

    return ExtractionResult(
        entities=entities,
        concepts=concepts,
        relations=relations,
        propositions=propositions,
        procedure=procedure,
        table_semantic=table_semantic,
    )


# ── Builder functions (dict → Pydantic model) ────────


def _build_entities(raw: list[dict]) -> list[ExtractedNamedEntity]:
    entities = []
    for item in raw:
        try:
            entities.append(
                ExtractedNamedEntity(
                    label=item["label"],
                    entity_type=item.get("entity_type", "Unknown"),
                    description=item.get("description"),
                )
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"Skipping malformed entity: {e}")
    return entities


def _build_concepts(raw: list[dict]) -> list[ExtractedConcept]:
    concepts = []
    for item in raw:
        try:
            concepts.append(
                ExtractedConcept(
                    name=item["name"],
                    definition=item.get("definition", ""),
                    aliases=item.get("aliases", []),
                )
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"Skipping malformed concept: {e}")
    return concepts


def _build_relationships(raw: list[dict]) -> list[ExtractedRelationship]:
    relations = []
    for item in raw:
        try:
            relations.append(
                ExtractedRelationship(
                    source_label=item["source_label"],
                    edge_type=item["edge_type"],
                    target_label=item["target_label"],
                    confidence=item.get("confidence", 1.0),
                )
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"Skipping malformed relationship: {e}")
    return relations


def _build_propositions(
    raw: list[dict], chunk_id: str
) -> list[ExtractedProposition]:
    props = []
    for item in raw:
        try:
            props.append(
                ExtractedProposition(
                    subject=item["subject"],
                    predicate=item["predicate"],
                    object=item["object"],
                    chunk_id=chunk_id,
                )
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"Skipping malformed proposition: {e}")
    return props


def _build_procedure(raw: dict | None, source_chunk: str) -> ExtractedProcedure | None:
    if raw is None:
        return None
    try:
        steps = []
        for i, s in enumerate(raw.get("steps", [])):
            try:
                # LLM may return "1.1" or "Step 1" for step_number — coerce to int
                raw_step_num = s.get("step_number", i + 1)
                step_num = int(float(str(raw_step_num))) if raw_step_num is not None else i + 1

                # LLM may return None or non-list for prerequisites
                raw_prereqs = s.get("prerequisites") or []
                prereqs = [int(float(str(p))) for p in raw_prereqs if isinstance(p, (int, float, str))]

                steps.append(ProcedureStep(
                    step_number=step_num,
                    description=s.get("description", ""),
                    prerequisites=prereqs,
                    responsible=s.get("responsible"),
                ))
            except (ValueError, TypeError):
                steps.append(ProcedureStep(
                    step_number=i + 1,
                    description=s.get("description", str(s)),
                ))
        return ExtractedProcedure(
            name=raw.get("name", "Unnamed Procedure"),
            intent=raw.get("intent", ""),
            steps=steps,
            source_chunk=source_chunk,
        )
    except (KeyError, TypeError) as e:
        logger.warning(f"Failed to build procedure: {e}")
        return None


def _build_table_semantic(raw: dict | None) -> ExtractedTableSemantic | None:
    if raw is None:
        return None
    try:
        columns = [
            ColumnSemantic(
                column_name=c["column_name"],
                description=c.get("description", ""),
                is_key=c.get("is_key", False),
            )
            for c in raw.get("columns", [])
        ]
        return ExtractedTableSemantic(
            table_name=raw.get("table_name", "unknown"),
            description=raw.get("description", ""),
            columns=columns,
        )
    except (KeyError, TypeError) as e:
        logger.warning(f"Failed to build table semantic: {e}")
        return None
