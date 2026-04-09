"""
Pydantic data models — the shared vocabulary for the entire system.

Every data structure that crosses a module boundary is defined here.
Models are grouped by lifecycle stage:

    Enums               — DocumentType, PipelineStage, ProviderStatus
    Context Provider    — ContextProvider (the top-level knowledge base entity)
    Ingestion           — IngestRequest, ParseResult, KnowledgeChunk, PipelineEvent
    Extraction          — entities, concepts, relationships, propositions, procedures
    Store               — KnowledgeStoreEntry, ProceduralStoreEntry (Milvus row shapes)
    Query               — QueryRequest, QueryResponse, ReasoningSubgraph

Consumed by every module in the backend.
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────


class DocumentType(str, Enum):
    """Supported document types for ingestion. Determines parsing strategy."""
    PDF = "pdf"
    TEXT = "text"
    CSV = "csv"
    SOP = "sop"    # Standard Operating Procedure — no chunking, full-text procedure extraction
    DDL = "ddl"    # SQL DDL — table semantics extraction + standard chunking
    WEB = "web"    # URL-based — fetched via HTTP, parsed as HTML by Docling


class PipelineStage(str, Enum):
    """Stages of the ingestion pipeline, emitted as SSE events to the UI."""
    PARSE = "parse"      # Docling converts raw file to structured text
    CHUNK = "chunk"      # HybridChunker splits text (or SOP bypass)
    EXTRACT = "extract"  # Unified LLM extraction (1 call per chunk)
    RESOLVE = "resolve"  # Semantic deduplication via GN index
    STORE = "store"      # Write to Neo4j + Milvus (KS, PS, GN)
    DONE = "done"        # Pipeline completed successfully
    ERROR = "error"      # Fatal error — pipeline aborted


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
    edge vocabulary defined in graph_constants.py.  Carries a free-text
    description for context and a confidence score from the LLM."""

    source_label: str  # must match an extracted entity label
    edge_type: str  # from EDGE_VOCABULARY
    target_label: str  # must match an extracted entity label
    description: str = ""  # brief context, e.g. "acquired in 2017"
    confidence: float = 1.0  # 1.0=explicit, 0.7-0.9=implied, <0.7=inferred


class ExtractedProposition(BaseModel):
    """A specific factual assertion from the document, structured as a
    (subject, predicate, object) triple. Tied to a chunk for provenance.
    Example: subject="CID-44821", predicate="has bandwidth", object="100 Mbps"."""

    subject: str
    predicate: str
    object: str
    chunk_id: str  # back-reference to source chunk


class ProcedureStep(BaseModel):
    """A single step in a Standard Operating Procedure. Steps form a DAG
    in Neo4j via PRECEDES edges based on the prerequisites list."""
    step_number: int
    description: str
    prerequisites: list[int] = []   # step_numbers that must complete first
    responsible: str | None = None  # team or role responsible for this step


class ExtractedProcedure(BaseModel):
    """A full SOP extracted from document text. Stored as a DAG in Neo4j:
    Procedure -[HAS_STEP]-> Step -[PRECEDES]-> Step -[REFERENCES]-> Entity."""
    name: str
    intent: str  # one-line summary — used as embedding input for PS and GN
    steps: list[ProcedureStep]
    source_chunk: str  # chunk_id of the source text


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
    """A row in the Milvus Knowledge Store (ks_{provider_id} collection).
    One entry per document chunk, with its embedding for ANN search."""
    chunk_id: str
    provider_id: str
    source_file: str
    doc_type: str
    text: str
    embedding: list[float]  # dimension matches EMBEDDING_DIM setting
    char_start: int
    char_end: int


class ProceduralStoreEntry(BaseModel):
    """A row in the Milvus Procedural Store (ps_{provider_id} collection).
    One entry per SOP, embedded by intent for procedure retrieval."""
    procedure_id: str = Field(default_factory=lambda: str(uuid4()))
    provider_id: str
    name: str
    intent: str
    steps_json: str  # JSON-serialised list[ProcedureStep]
    embedding: list[float]  # embed(intent), dimension matches EMBEDDING_DIM


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
    description: str = ""
    confidence: float | None = None


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
