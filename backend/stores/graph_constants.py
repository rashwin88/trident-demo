"""
Graph edge vocabulary — the constrained set of relationship types.

All edges created in the knowledge graph must use a type from this vocabulary.
This ensures consistent graph structure and enables reliable traversal patterns.
The vocabulary is domain-agnostic enough for telecom, enterprise, and general
knowledge bases, but specific enough to carry semantic meaning.

Edges carry three properties:
    - description: free-text context for the relationship (from LLM extraction)
    - confidence:  0.0–1.0 score indicating extraction confidence
    - provider_id: scoping provider UUID (inherited from the nodes)

Imported by:
    - stores/graph.py (edge creation validation)
    - ingestion/dspy_programs.py (Literal type enforcement via EdgeType)
    - agent/tools.py (relationship creation tool)
"""

# Every edge type, its typical direction, and what it means:
#
# STRUCTURAL (document → chunk → extracted items — created by pipeline code):
#   CONTAINS:       Document → Chunk (document contains this text segment)
#   MENTIONS:       Chunk → Entity (text segment names this entity)
#   DEFINES:        Chunk → Concept (text segment defines this concept)
#   ASSERTS:        Chunk → Proposition (text segment states this fact)
#
# PROCEDURAL (SOP DAG structure — created by pipeline code):
#   HAS_STEP:       Procedure → Step (procedure includes this step)
#   PRECEDES:       Step → Step (this step must complete before the next)
#   REFERENCES:     Step → Entity (step description mentions this entity)
#
# SEMANTIC (extracted entity relationships — produced by LLM):
#   RELATED_TO:     Entity ↔ Entity (general semantic relationship — use when no specific type fits)
#   INSTANCE_OF:    Entity → Concept (entity is an instance of a category)
#   PART_OF:        Entity → Entity (component or subdivision)
#   GOVERNED_BY:    Entity → Entity (regulatory or policy authority)
#   CLASSIFIED_AS:  Entity → Entity (type or class categorization)
#   TERMINATES_AT:  Entity → Entity (circuit/service endpoint)
#   PROVISIONED_FROM: Entity → Entity (service origin or deployment source)
#   BILLED_ON:      Entity → Entity (billing relationship)
#   RECONCILES_TO:  Entity → Entity (cross-system record match)
#   FLAGS:          Entity → Entity (issue, alert, or exception flag)
#   DESCRIBED_BY:   Entity → Entity (documentation or specification link)
#   IMPLEMENTED_BY: Entity → Entity (team or system that builds/operates)
#   SUPERSEDES:     Entity → Entity (version replacement)
#   SOURCED_FROM:   Entity → Entity (data origin)
#   LOCATED_IN:     Entity → Entity (geographic or logical containment)
#   DEPENDS_ON:     Entity → Entity (technical or operational dependency)
#   OPERATES:       Entity → Entity (org/team runs or manages a service)
#   ACQUIRED_BY:    Entity → Entity (corporate acquisition or merger)
#   USES:           Entity → Entity (system or process uses a technology)
#   CONNECTS_TO:    Entity → Entity (network/integration link between systems)
#   MANAGES:        Entity → Entity (person or team manages an entity)
#   OTHER:          Entity → Entity (catch-all — description field carries the semantics)

EDGE_VOCABULARY: set[str] = {
    # Structural (pipeline code only)
    "CONTAINS",
    "MENTIONS",
    "DEFINES",
    "ASSERTS",
    # Procedural (pipeline code only)
    "HAS_STEP",
    "PRECEDES",
    "REFERENCES",
    # Semantic (LLM-extracted)
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
}

# Sorted list for reference (deterministic ordering).
EDGE_VOCABULARY_LIST: list[str] = sorted(EDGE_VOCABULARY)
