import json
import logging

import dspy

from stores.graph import EDGE_VOCABULARY_LIST

logger = logging.getLogger(__name__)


# ── DSPy Signatures ──────────────────────────────────


class NamedEntitySignature(dspy.Signature):
    """Extract named entities from a telecom/business document chunk.
    Return a JSON list of {label, entity_type, description} objects."""

    chunk_text: str = dspy.InputField()
    entities: str = dspy.OutputField()


class ConceptSignature(dspy.Signature):
    """Extract key concepts and their definitions from this document chunk.
    Return a JSON list of {name, definition, aliases} objects."""

    chunk_text: str = dspy.InputField()
    concepts: str = dspy.OutputField()


class RelationshipSignature(dspy.Signature):
    """Extract relationships between the provided entities.
    Only use entity labels from the provided list.
    Edge types must come from the allowed vocabulary.
    Return a JSON list of {source_label, edge_type, target_label, confidence} objects."""

    chunk_text: str = dspy.InputField()
    entity_labels: str = dspy.InputField()
    allowed_edges: str = dspy.InputField()
    relationships: str = dspy.OutputField()


class PropositionSignature(dspy.Signature):
    """Extract factual propositions as (subject, predicate, object) triples.
    Return a JSON list of {subject, predicate, object} objects."""

    chunk_text: str = dspy.InputField()
    propositions: str = dspy.OutputField()


class ProcedureSignature(dspy.Signature):
    """Extract a structured procedure with ordered steps from this SOP text.
    Return a JSON object with {name, intent, steps} where steps is a list
    of {step_number, description, prerequisites, responsible} objects."""

    chunk_text: str = dspy.InputField()
    procedure: str = dspy.OutputField()


class DBSemanticsSignature(dspy.Signature):
    """Given this SQL DDL, return semantic descriptions for each table and column.
    Return a JSON object with {table_name, description, columns} where columns
    is a list of {column_name, description, is_key} objects."""

    ddl_text: str = dspy.InputField()
    semantics: str = dspy.OutputField()


# ── Extraction Pipeline ──────────────────────────────


class FullExtractionPipeline:
    """Runs all extraction modules on a single chunk."""

    def __init__(self) -> None:
        self.entity_mod = dspy.ChainOfThought(NamedEntitySignature)
        self.concept_mod = dspy.ChainOfThought(ConceptSignature)
        self.rel_mod = dspy.ChainOfThought(RelationshipSignature)
        self.prop_mod = dspy.ChainOfThought(PropositionSignature)
        self.procedure_mod = dspy.ChainOfThought(ProcedureSignature)
        self.db_semantics_mod = dspy.ChainOfThought(DBSemanticsSignature)

    def extract_entities(self, chunk_text: str) -> list[dict]:
        result = self.entity_mod(chunk_text=chunk_text)
        return _parse_json_list(result.entities, "entities")

    def extract_concepts(self, chunk_text: str) -> list[dict]:
        result = self.concept_mod(chunk_text=chunk_text)
        return _parse_json_list(result.concepts, "concepts")

    def extract_relationships(
        self, chunk_text: str, entity_labels: list[str]
    ) -> list[dict]:
        result = self.rel_mod(
            chunk_text=chunk_text,
            entity_labels=json.dumps(entity_labels),
            allowed_edges=json.dumps(EDGE_VOCABULARY_LIST),
        )
        return _parse_json_list(result.relationships, "relationships")

    def extract_propositions(self, chunk_text: str) -> list[dict]:
        result = self.prop_mod(chunk_text=chunk_text)
        return _parse_json_list(result.propositions, "propositions")

    def extract_procedure(self, chunk_text: str) -> dict | None:
        result = self.procedure_mod(chunk_text=chunk_text)
        return _parse_json_object(result.procedure, "procedure")

    def extract_db_semantics(self, ddl_text: str) -> dict | None:
        result = self.db_semantics_mod(ddl_text=ddl_text)
        return _parse_json_object(result.semantics, "db_semantics")


# ── JSON parsing helpers ─────────────────────────────


def _parse_json_list(raw: str, label: str) -> list[dict]:
    try:
        parsed = json.loads(_clean_json(raw))
        if isinstance(parsed, list):
            return parsed
        logger.warning(f"Expected list for {label}, got {type(parsed).__name__}")
        return []
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse {label} JSON: {e}")
        return []


def _parse_json_object(raw: str, label: str) -> dict | None:
    try:
        parsed = json.loads(_clean_json(raw))
        if isinstance(parsed, dict):
            return parsed
        logger.warning(f"Expected dict for {label}, got {type(parsed).__name__}")
        return None
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse {label} JSON: {e}")
        return None


def _clean_json(raw: str) -> str:
    """Strip markdown code fences if the LLM wraps JSON in them."""
    if not raw:
        return ""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return text
