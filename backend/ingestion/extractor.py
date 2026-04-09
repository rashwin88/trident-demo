"""Knowledge extraction module — converts raw LLM output into typed Pydantic models.

Sits between the DSPy extraction pipeline (which returns raw dicts) and the
graph/store layer (which expects validated Pydantic models).  The public
function extract_from_chunk orchestrates a single unified LLM call and then
delegates to _build_* helpers that safely coerce the LLM's JSON into the
corresponding Pydantic models, logging and skipping any malformed items.

Consumed by:
    - ingestion.pipeline  (calls extract_from_chunk for each KnowledgeChunk)

Key design choices:
    - Each _build_* function is tolerant of missing/malformed keys because
      LLM output is inherently unpredictable.
    - Procedure step numbers are coerced through int(float(str(x))) because
      the LLM sometimes returns "1.1" or "Step 1" instead of plain ints.
"""

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
    """Extract all knowledge-graph elements from a single chunk.

    Makes one unified LLM call via the pipeline, then converts the raw
    dicts into validated Pydantic models.

    Args:
        chunk:    The KnowledgeChunk to extract from.
        pipeline: A configured FullExtractionPipeline instance.

    Returns:
        ExtractionResult containing lists of entities, concepts,
        relationships, and propositions.
    """
    text = chunk.text

    # One LLM call for everything
    raw = pipeline.extract_unified(text)

    entities = _build_entities(raw["entities"])
    concepts = _build_concepts(raw["concepts"])
    relations = _build_relationships(raw["relationships"])
    propositions = _build_propositions(raw["propositions"], chunk.chunk_id)

    return ExtractionResult(
        entities=entities,
        concepts=concepts,
        relations=relations,
        propositions=propositions,
    )


# ── Builder functions (dict → Pydantic model) ────────


def _build_entities(raw: list[dict]) -> list[ExtractedNamedEntity]:
    """Convert raw entity dicts into ExtractedNamedEntity models.

    Args:
        raw: List of dicts with keys label, entity_type, description.

    Returns:
        List of validated models; malformed items are logged and skipped.
    """
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
    """Convert raw concept dicts into ExtractedConcept models.

    Args:
        raw: List of dicts with keys name, definition, aliases.

    Returns:
        List of validated models; malformed items are logged and skipped.
    """
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
    """Convert raw relationship dicts into ExtractedRelationship models.

    Edge types are enforced at the LLM level via the Literal-typed Pydantic
    output model in dspy_programs.py — the LLM cannot return invalid types.
    A safety-net validation is kept here as defense-in-depth.

    Args:
        raw: List of dicts with keys source_label, edge_type, target_label,
             and optional confidence.

    Returns:
        List of validated models; malformed items are logged and skipped.
    """
    from stores.graph_constants import EDGE_VOCABULARY

    relations = []
    for item in raw:
        try:
            edge_type = item["edge_type"]
            if edge_type not in EDGE_VOCABULARY:
                logger.warning(f"Dropping invalid edge type '{edge_type}' (should not happen with typed output)")
                continue
            relations.append(
                ExtractedRelationship(
                    source_label=item["source_label"],
                    edge_type=edge_type,
                    target_label=item["target_label"],
                    description=item.get("description", ""),
                    confidence=item.get("confidence", 1.0),
                )
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"Skipping malformed relationship: {e}")
    return relations


def _build_propositions(
    raw: list[dict], chunk_id: str
) -> list[ExtractedProposition]:
    """Convert raw proposition dicts into ExtractedProposition models.

    Args:
        raw:      List of dicts with keys subject, predicate, object.
        chunk_id: ID of the source chunk, attached for provenance.

    Returns:
        List of validated models; malformed items are logged and skipped.
    """
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
    """Convert a raw procedure dict into an ExtractedProcedure model.

    Handles common LLM output quirks: step_number may be a float string
    ("1.1"), prerequisites may be None instead of an empty list, etc.

    Args:
        raw:          Dict with keys name, intent, steps -- or None.
        source_chunk: ID of the source chunk, for provenance.

    Returns:
        ExtractedProcedure with coerced step numbers, or None on failure.
    """
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
    """Convert a raw table-semantic dict into an ExtractedTableSemantic model.

    Args:
        raw: Dict with keys table_name, description, columns -- or None.

    Returns:
        ExtractedTableSemantic with column metadata, or None on failure.
    """
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
