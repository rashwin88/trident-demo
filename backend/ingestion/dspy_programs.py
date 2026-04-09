"""DSPy signatures and extraction pipeline for knowledge-graph construction.

Defines the LLM prompt signatures (via DSPy) and the orchestrating
FullExtractionPipeline class that turns a chunk of text into structured
knowledge: entities, concepts, relationships, and propositions.

Three extraction modes are supported:
    - Unified extraction (general documents) -- one LLM call per chunk.
    - Procedure extraction (SOPs) -- extracts ordered steps with prerequisites.
    - DB-semantics extraction (DDL) -- produces human-readable column descriptions.

DENSITY_PROMPTS controls how aggressively the LLM extracts facts, allowing the
pipeline operator to trade thoroughness for cost/speed.

Consumed by:
    - ingestion.extractor  (instantiates FullExtractionPipeline, calls its methods)
    - ingestion.pipeline   (passes chunks through the extractor stage)

Key design choices:
    - DSPy ChainOfThought is used so the LLM reasons before emitting JSON,
      which measurably improves extraction quality on complex chunks.
    - Edge types are enforced via a Literal type on the Pydantic output model.
      The LLM's structured output mode prevents hallucinated edge types at
      the API level — no post-hoc filtering needed.
"""

import json
import logging
from typing import Literal

import dspy
from pydantic import BaseModel, Field

from config import settings

logger = logging.getLogger(__name__)

# ── Density presets ──────────────────────────────────

DENSITY_PROMPTS = {
    "low": (
        "Extract only the most important entities (3-5), concepts (1-3), "
        "relationships (2-4), and propositions (2-4). "
        "Focus on the core facts — skip minor details."
    ),
    "medium": (
        "Extract a thorough set of entities (8-15), concepts (3-6), "
        "relationships (6-12), and propositions (5-10). "
        "Capture all named entities (people, orgs, products, technologies) "
        "and their connections. Do not skip any proper nouns."
    ),
    "high": (
        "Extract comprehensively: all entities, concepts, relationships, "
        "and propositions you can identify. Be thorough — capture every "
        "fact, name, term, and connection in the text."
    ),
}


# ── Typed output models (Pydantic) ─────────────────
# These enforce the schema at the LLM API level via structured output.
# The Literal type on edge_type means the LLM *cannot* return a value
# outside the vocabulary — no hallucinated edge types.

EdgeType = Literal[
    "RELATED_TO",
    "INSTANCE_OF",
    "PART_OF",
    "GOVERNED_BY",
    "CLASSIFIED_AS",
    "TERMINATES_AT",
    "PROVISIONED_FROM",
    "BILLED_ON",
    "RECONCILES_TO",
    "FLAGS",
    "DESCRIBED_BY",
    "IMPLEMENTED_BY",
    "SUPERSEDES",
    "SOURCED_FROM",
    "LOCATED_IN",
    "DEPENDS_ON",
    "OPERATES",
    "ACQUIRED_BY",
    "USES",
    "CONNECTS_TO",
    "MANAGES",
    "OTHER",
]


class EntityOutput(BaseModel):
    label: str = Field(description="Full canonical name with acronym, e.g. 'Meridian Edge Node (MEN)'")
    entity_type: str = Field(description="Person, Organization, Location, Device, Service, Model, Protocol, Interface, Framework, Platform, Policy, Standard, Database, Circuit, Data, or Classification")
    description: str = Field(default="", description="Brief description of the entity in context")


class ConceptOutput(BaseModel):
    name: str = Field(description="Concept name")
    definition: str = Field(default="", description="One-sentence definition")
    aliases: list[str] = Field(default_factory=list, description="Alternative names or acronyms")


class RelationshipOutput(BaseModel):
    source_label: str = Field(description="Label of the source entity (must match an extracted entity)")
    edge_type: EdgeType = Field(description=(
        "Relationship type. Choose the most specific: "
        "PART_OF=component/subdivision, "
        "INSTANCE_OF=instance of a category, "
        "GOVERNED_BY=regulated by policy/authority, "
        "CLASSIFIED_AS=categorized as type/class, "
        "LOCATED_IN=geographic or logical containment (org in city, service in region), "
        "DEPENDS_ON=technical/operational dependency, "
        "OPERATES=org/team runs a service, "
        "USES=system uses a technology, "
        "IMPLEMENTED_BY=built or operated by team/system, "
        "ACQUIRED_BY=corporate acquisition or merger, "
        "CONNECTS_TO=network/integration link, "
        "MANAGES=person/team manages an entity, "
        "TERMINATES_AT=service endpoint, "
        "PROVISIONED_FROM=deployed from a source, "
        "DESCRIBED_BY=documented by, "
        "SOURCED_FROM=data originates from, "
        "SUPERSEDES=replaces previous version, "
        "FLAGS=flags an issue/alert, "
        "BILLED_ON=billing relationship, "
        "RECONCILES_TO=cross-system record match, "
        "RELATED_TO=general link (last resort), "
        "OTHER=none of the above (put details in description)"
    ))
    target_label: str = Field(description="Label of the target entity (must match an extracted entity)")
    description: str = Field(default="", description="Brief context for the relationship, e.g. 'acquired in 2017 for $4.5B'")
    confidence: float = Field(default=1.0, description="Confidence 0-1: 1.0=explicitly stated, 0.7-0.9=strongly implied, <0.7=inferred")


class PropositionOutput(BaseModel):
    subject: str = Field(description="Subject entity or noun phrase (use an extracted entity label when possible)")
    predicate: str = Field(description="Verb or verb phrase expressing the relationship, e.g. 'is headquartered in', 'was deployed in', 'runs on'")
    object: str = Field(description="Object entity, value, or noun phrase. For factual claims: dates, quantities, versions, locations. Do NOT duplicate relationships already captured as edges.")


class ExtractionOutput(BaseModel):
    """Complete extraction result from a document chunk."""
    entities: list[EntityOutput] = Field(default_factory=list)
    concepts: list[ConceptOutput] = Field(default_factory=list)
    relationships: list[RelationshipOutput] = Field(default_factory=list)
    propositions: list[PropositionOutput] = Field(default_factory=list)


# ── Unified Extraction Signature ─────────────────────


class UnifiedExtractionSignature(dspy.Signature):
    """Extract a knowledge graph from this document chunk.

    Rules:
    - Use the FULL canonical name as the entity label (e.g. "Meridian Edge Node (MEN)" not just "MEN"). If an acronym is introduced, include both forms.
    - entity_type should be specific: a machine learning model is "Model" not "Service"; a protocol is "Protocol" not "Service".
    - Prefer specific relationship types (PART_OF, PROVISIONED_FROM, GOVERNED_BY, IMPLEMENTED_BY) over generic RELATED_TO. Only use RELATED_TO when no specific type fits.
    - relationships MUST use labels from the entities you extracted.
    - Extract ALL named people, organizations, products, and technologies — do not skip any.
    - propositions are factual claims (subject-predicate-object) grounded in the text. Focus on facts that carry specific data: dates, quantities, versions, configurations, locations. Use entity labels as subject when possible. Do NOT duplicate entity-to-entity relationships already captured as edges — propositions are for facts like "Meridian was first deployed in Q3 2024" or "AnomalyNet accepts a 60-second sliding window".
    """

    chunk_text: str = dspy.InputField()
    density_instruction: str = dspy.InputField()
    extraction: ExtractionOutput = dspy.OutputField()


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
    """Orchestrates LLM-based knowledge extraction from text chunks.

    Each chunk is processed with a single unified LLM call that returns
    entities, concepts, relationships, and propositions simultaneously.
    The output is a typed Pydantic model (ExtractionOutput), enforced
    by the LLM's structured output mode — edge types cannot be hallucinated.

    Separate methods handle SOP procedure extraction and DDL semantic
    annotation for specialised document types.

    The density parameter (low / medium / high) controls extraction
    aggressiveness and is set once at construction time.
    """

    def __init__(self, density: str | None = None) -> None:
        self._density = density or settings.EXTRACTION_DENSITY
        self._unified_mod = dspy.ChainOfThought(UnifiedExtractionSignature)
        self._procedure_mod = dspy.ChainOfThought(ProcedureSignature)
        self._db_semantics_mod = dspy.ChainOfThought(DBSemanticsSignature)

    @property
    def density(self) -> str:
        return self._density

    def extract_unified(self, chunk_text: str) -> dict:
        """Run a single LLM call to extract all knowledge-graph elements.

        The LLM returns a typed ExtractionOutput via structured output.
        Edge types are constrained by the Literal type — the LLM cannot
        return values outside the vocabulary.

        Args:
            chunk_text: The text of one document chunk.

        Returns:
            Dict with keys "entities", "concepts", "relationships",
            "propositions" -- each a list of dicts.  Returns empty lists
            on parse failure so callers never need to handle None.
        """
        density_instruction = DENSITY_PROMPTS.get(self._density, DENSITY_PROMPTS["medium"])

        try:
            result = self._unified_mod(
                chunk_text=chunk_text,
                density_instruction=density_instruction,
            )

            extraction = result.extraction

            # DSPy returns the typed Pydantic model directly
            if isinstance(extraction, ExtractionOutput):
                return {
                    "entities": [e.model_dump() for e in extraction.entities],
                    "concepts": [c.model_dump() for c in extraction.concepts],
                    "relationships": [r.model_dump() for r in extraction.relationships],
                    "propositions": [p.model_dump() for p in extraction.propositions],
                }

            # Fallback: DSPy returned a raw string (older versions or config)
            if isinstance(extraction, str):
                parsed = _parse_json_object(extraction, "unified_extraction")
                if not parsed:
                    return {"entities": [], "concepts": [], "relationships": [], "propositions": []}
                return {
                    "entities": parsed.get("entities", []) if isinstance(parsed.get("entities"), list) else [],
                    "concepts": parsed.get("concepts", []) if isinstance(parsed.get("concepts"), list) else [],
                    "relationships": parsed.get("relationships", []) if isinstance(parsed.get("relationships"), list) else [],
                    "propositions": parsed.get("propositions", []) if isinstance(parsed.get("propositions"), list) else [],
                }

            # Fallback: dict already
            if isinstance(extraction, dict):
                return extraction

            logger.warning(f"Unexpected extraction type: {type(extraction)}")
            return {"entities": [], "concepts": [], "relationships": [], "propositions": []}

        except Exception as e:
            logger.warning(f"Unified extraction failed: {e}")
            return {"entities": [], "concepts": [], "relationships": [], "propositions": []}

    def extract_procedure(self, chunk_text: str) -> dict | None:
        """Extract a structured procedure from SOP text.

        Args:
            chunk_text: Text containing a standard operating procedure.

        Returns:
            Dict with keys name, intent, steps (list of step dicts),
            or None if parsing fails.
        """
        result = self._procedure_mod(chunk_text=chunk_text)
        return _parse_json_object(result.procedure, "procedure")

    def extract_db_semantics(self, ddl_text: str) -> dict | None:
        """Extract human-readable semantic descriptions from SQL DDL.

        Args:
            ddl_text: Raw SQL DDL (CREATE TABLE statements).

        Returns:
            Dict with keys table_name, description, columns (list of
            column dicts), or None if parsing fails.
        """
        result = self._db_semantics_mod(ddl_text=ddl_text)
        return _parse_json_object(result.semantics, "db_semantics")


# ── JSON parsing helpers ─────────────────────────────


def _parse_json_list(raw: str, label: str) -> list[dict]:
    """Parse a JSON string that should be a list of dicts.

    Args:
        raw:   Raw JSON string (may be wrapped in markdown code fences).
        label: Human-readable label for log messages on failure.

    Returns:
        Parsed list, or empty list on any parse error.
    """
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
    """Parse a JSON string that should be a dict.

    Args:
        raw:   Raw JSON string (may be wrapped in markdown code fences).
        label: Human-readable label for log messages on failure.

    Returns:
        Parsed dict, or None on any parse error.
    """
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
