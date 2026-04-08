from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────


class DocumentType(str, Enum):
    PDF = "pdf"
    TEXT = "text"
    CSV = "csv"
    SOP = "sop"
    DDL = "ddl"
    WEB = "web"


class PipelineStage(str, Enum):
    PARSE = "parse"
    CHUNK = "chunk"
    EXTRACT = "extract"
    RESOLVE = "resolve"
    STORE = "store"
    DONE = "done"
    ERROR = "error"


class ProviderStatus(str, Enum):
    READY = "ready"
    INGESTING = "ingesting"
    ERROR = "error"


# ── Context Provider ─────────────────────────────────


class ContextProvider(BaseModel):
    provider_id: str
    name: str
    description: str
    status: ProviderStatus = ProviderStatus.READY
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    doc_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    chunk_count: int = 0
    last_ingested_at: datetime | None = None


# ── Ingestion ─────────────────────────────────────────


class IngestRequest(BaseModel):
    provider_id: str
    document_type: DocumentType
    filename: str


class ParseResult(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    text: str
    metadata: dict
    doc_type: DocumentType
    docling_document: Any = None  # DoclingDocument — passed to Docling chunker


class KnowledgeChunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid4()))
    provider_id: str
    source_file: str
    doc_type: DocumentType
    text: str
    char_start: int
    char_end: int
    embedding: list[float] | None = None


class PipelineEvent(BaseModel):
    stage: PipelineStage
    message: str
    detail: dict | None = None


# ── Extraction Models ─────────────────────────────────


class ExtractedNamedEntity(BaseModel):
    """A concrete, named thing found in the text — a circuit ID, a carrier,
    a network element, a person, etc."""

    label: str  # e.g. "CID-44821", "BT", "LON-CE-01"
    entity_type: str  # e.g. "Circuit", "Carrier", "NetworkElement"
    description: str | None = None


class ExtractedConcept(BaseModel):
    """A reusable definition or idea — like a glossary entry.
    Example: name="Monthly Recurring Charge",
    definition="A fixed fee billed each month for a contracted telecom service",
    aliases=["MRC"]."""

    name: str
    definition: str
    aliases: list[str] = []


class ExtractedRelationship(BaseModel):
    """A directed edge between two extracted entities, constrained to the
    20-type edge vocabulary defined in the spec."""

    source_label: str  # must match an extracted entity label
    edge_type: str  # from EDGE_VOCABULARY
    target_label: str  # must match an extracted entity label
    confidence: float = 1.0


class ExtractedProposition(BaseModel):
    """A specific factual assertion from the document, structured as a
    (subject, predicate, object) triple. Tied to a chunk for provenance.
    Example: subject="CID-44821", predicate="has bandwidth", object="100 Mbps"."""

    subject: str
    predicate: str
    object: str
    chunk_id: str  # back-reference to source chunk


class ProcedureStep(BaseModel):
    step_number: int
    description: str
    prerequisites: list[int] = []
    responsible: str | None = None


class ExtractedProcedure(BaseModel):
    name: str
    intent: str  # one-line summary — used as embedding input
    steps: list[ProcedureStep]
    source_chunk: str


class ColumnSemantic(BaseModel):
    column_name: str
    description: str
    is_key: bool = False


class ExtractedTableSemantic(BaseModel):
    table_name: str
    description: str
    columns: list[ColumnSemantic]


class ExtractionResult(BaseModel):
    entities: list[ExtractedNamedEntity] = []
    concepts: list[ExtractedConcept] = []
    relations: list[ExtractedRelationship] = []
    propositions: list[ExtractedProposition] = []
    procedure: ExtractedProcedure | None = None
    table_semantic: ExtractedTableSemantic | None = None


# ── Store Models ──────────────────────────────────────


class KnowledgeStoreEntry(BaseModel):
    chunk_id: str
    provider_id: str
    source_file: str
    doc_type: str
    text: str
    embedding: list[float]  # dim=768
    char_start: int
    char_end: int


class ProceduralStoreEntry(BaseModel):
    procedure_id: str = Field(default_factory=lambda: str(uuid4()))
    provider_id: str
    name: str
    intent: str
    steps_json: str  # JSON-serialised list[ProcedureStep]
    embedding: list[float]  # embed(intent), dim=768


# ── Query Models ──────────────────────────────────────


class QueryRequest(BaseModel):
    provider_id: str
    question: str
    top_k: int = 5  # chunks from Knowledge Store
    graph_hops: int = 2  # BFS depth from matched entities


class GraphNode(BaseModel):
    node_id: str
    label: str  # Neo4j node label
    properties: dict
    relevance: float | None = None


class GraphEdge(BaseModel):
    source: str  # node_id
    target: str  # node_id
    edge_type: str


class ReasoningSubgraph(BaseModel):
    """The exact nodes and edges that contributed to the answer."""
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    anchor_node_ids: list[str]  # semantic search entry points


class QueryResponse(BaseModel):
    answer: str
    reasoning_subgraph: ReasoningSubgraph  # the "why" — full path through the graph
    graph_nodes: list[GraphNode]  # flat list for backwards compat
    chunks_used: list[str]  # chunk_ids used in answer
    procedures: list[str]  # procedure names retrieved (if any)
    provider_id: str
