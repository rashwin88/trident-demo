import json
import logging

import dspy

from config import settings
from stores.graph import EDGE_VOCABULARY_LIST

logger = logging.getLogger(__name__)

# ── Density presets ──────────────────────────────────

DENSITY_PROMPTS = {
    "low": (
        "Extract only the most important entities (3-5), concepts (1-3), "
        "relationships (2-4), and propositions (2-4). "
        "Focus on the core facts — skip minor details."
    ),
    "medium": (
        "Extract a balanced set of entities (5-10), concepts (2-5), "
        "relationships (4-8), and propositions (4-8). "
        "Capture the main facts and their connections."
    ),
    "high": (
        "Extract comprehensively: all entities, concepts, relationships, "
        "and propositions you can identify. Be thorough — capture every "
        "fact, name, term, and connection in the text."
    ),
}


# ── Unified Extraction Signature ─────────────────────


class UnifiedExtractionSignature(dspy.Signature):
    """Extract a knowledge graph from this document chunk in a single pass.

    Return a JSON object with four arrays:
    {
      "entities": [{label, entity_type, description}],
      "concepts": [{name, definition, aliases}],
      "relationships": [{source_label, edge_type, target_label, confidence}],
      "propositions": [{subject, predicate, object}]
    }

    Rules:
    - entity_type: Person, Organization, Location, Device, Circuit, Service, etc.
    - edge_type MUST come from the allowed_edges list
    - relationships MUST use labels from the entities you extracted
    - propositions are factual triples grounded in the text
    - Connect propositions to entities: use entity labels as subject/object where possible
    """

    chunk_text: str = dspy.InputField()
    allowed_edges: str = dspy.InputField()
    density_instruction: str = dspy.InputField()
    extraction: str = dspy.OutputField()


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
    """Runs extraction on chunks. Uses a single unified LLM call per chunk."""

    def __init__(self, density: str | None = None) -> None:
        self._density = density or settings.EXTRACTION_DENSITY
        self._unified_mod = dspy.ChainOfThought(UnifiedExtractionSignature)
        self._procedure_mod = dspy.ChainOfThought(ProcedureSignature)
        self._db_semantics_mod = dspy.ChainOfThought(DBSemanticsSignature)

    @property
    def density(self) -> str:
        return self._density

    def extract_unified(self, chunk_text: str) -> dict:
        """Single LLM call → entities + concepts + relationships + propositions."""
        density_instruction = DENSITY_PROMPTS.get(self._density, DENSITY_PROMPTS["medium"])

        result = self._unified_mod(
            chunk_text=chunk_text,
            allowed_edges=json.dumps(EDGE_VOCABULARY_LIST),
            density_instruction=density_instruction,
        )

        parsed = _parse_json_object(result.extraction, "unified_extraction")
        if not parsed:
            return {"entities": [], "concepts": [], "relationships": [], "propositions": []}

        return {
            "entities": parsed.get("entities", []) if isinstance(parsed.get("entities"), list) else [],
            "concepts": parsed.get("concepts", []) if isinstance(parsed.get("concepts"), list) else [],
            "relationships": parsed.get("relationships", []) if isinstance(parsed.get("relationships"), list) else [],
            "propositions": parsed.get("propositions", []) if isinstance(parsed.get("propositions"), list) else [],
        }

    def extract_entities(self, chunk_text: str) -> list[dict]:
        """Extract only entities (used for per-step entity extraction in SOPs)."""
        result = self.extract_unified(chunk_text)
        return result["entities"]

    def extract_procedure(self, chunk_text: str) -> dict | None:
        result = self._procedure_mod(chunk_text=chunk_text)
        return _parse_json_object(result.procedure, "procedure")

    def extract_db_semantics(self, ddl_text: str) -> dict | None:
        result = self._db_semantics_mod(ddl_text=ddl_text)
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
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return text
