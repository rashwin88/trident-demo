import json

import pytest
from pydantic import ValidationError

from models import (
    ColumnSemantic,
    ContextProvider,
    DocumentType,
    ExtractionResult,
    ExtractedConcept,
    ExtractedNamedEntity,
    ExtractedProcedure,
    ExtractedProposition,
    ExtractedRelationship,
    ExtractedTableSemantic,
    GraphNode,
    IngestRequest,
    KnowledgeChunk,
    KnowledgeStoreEntry,
    ParseResult,
    PipelineEvent,
    PipelineStage,
    ProcedureStep,
    ProceduralStoreEntry,
    QueryRequest,
    QueryResponse,
)


# ── Enum tests ────────────────────────────────────────


class TestDocumentType:
    def test_all_members(self):
        assert set(DocumentType) == {
            DocumentType.PDF,
            DocumentType.TEXT,
            DocumentType.CSV,
            DocumentType.SOP,
            DocumentType.DDL,
        }

    def test_string_values(self):
        assert DocumentType.PDF == "pdf"
        assert DocumentType.SOP == "sop"
        assert DocumentType.DDL == "ddl"


class TestPipelineStage:
    def test_all_stages(self):
        assert len(PipelineStage) == 7

    def test_terminal_stages(self):
        assert PipelineStage.DONE == "done"
        assert PipelineStage.ERROR == "error"


# ── Context Provider ─────────────────────────────────


class TestContextProvider:
    def test_creation(self):
        p = ContextProvider(
            provider_id="test-provider",
            name="Test Provider",
            description="A test provider",
        )
        assert p.provider_id == "test-provider"
        assert p.doc_count == 0
        assert p.node_count == 0
        assert p.created_at is not None

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            ContextProvider(provider_id="x")  # type: ignore[call-arg]


# ── Ingestion models ─────────────────────────────────


class TestIngestRequest:
    def test_valid(self):
        r = IngestRequest(
            provider_id="p1",
            document_type=DocumentType.PDF,
            filename="test.pdf",
        )
        assert r.document_type == DocumentType.PDF

    def test_invalid_doc_type(self):
        with pytest.raises(ValidationError):
            IngestRequest(
                provider_id="p1",
                document_type="invalid",  # type: ignore[arg-type]
                filename="test.txt",
            )


class TestKnowledgeChunk:
    def test_auto_uuid(self):
        c1 = KnowledgeChunk(
            provider_id="p1",
            source_file="f.txt",
            doc_type=DocumentType.TEXT,
            text="hello",
            char_start=0,
            char_end=5,
        )
        c2 = KnowledgeChunk(
            provider_id="p1",
            source_file="f.txt",
            doc_type=DocumentType.TEXT,
            text="world",
            char_start=5,
            char_end=10,
        )
        assert c1.chunk_id != c2.chunk_id
        assert c1.embedding is None


class TestParseResult:
    def test_creation(self):
        pr = ParseResult(
            text="hello world",
            metadata={"page_count": 3},
            doc_type=DocumentType.PDF,
        )
        assert pr.metadata["page_count"] == 3


class TestPipelineEvent:
    def test_serialization(self):
        e = PipelineEvent(
            stage=PipelineStage.CHUNK,
            message="Created 10 chunks",
            detail={"count": 10},
        )
        data = json.loads(e.model_dump_json())
        assert data["stage"] == "chunk"
        assert data["detail"]["count"] == 10

    def test_no_detail(self):
        e = PipelineEvent(stage=PipelineStage.DONE, message="Done")
        assert e.detail is None


# ── Extraction models ────────────────────────────────


class TestExtractedNamedEntity:
    def test_with_description(self):
        e = ExtractedNamedEntity(
            label="CID-44821",
            entity_type="Circuit",
            description="A 100 Mbps circuit",
        )
        assert e.label == "CID-44821"

    def test_without_description(self):
        e = ExtractedNamedEntity(label="BT", entity_type="Carrier")
        assert e.description is None


class TestExtractedConcept:
    def test_with_aliases(self):
        c = ExtractedConcept(
            name="Monthly Recurring Charge",
            definition="Fixed monthly fee",
            aliases=["MRC"],
        )
        assert "MRC" in c.aliases

    def test_default_aliases(self):
        c = ExtractedConcept(name="Bandwidth", definition="Data rate")
        assert c.aliases == []


class TestExtractedRelationship:
    def test_defaults(self):
        r = ExtractedRelationship(
            source_label="CID-1",
            edge_type="TERMINATES_AT",
            target_label="LON-CE-01",
        )
        assert r.confidence == 1.0


class TestExtractedProposition:
    def test_creation(self):
        p = ExtractedProposition(
            subject="CID-44821",
            predicate="has bandwidth",
            object="100 Mbps",
            chunk_id="abc-123",
        )
        assert p.chunk_id == "abc-123"


class TestExtractedProcedure:
    def test_with_steps(self):
        proc = ExtractedProcedure(
            name="Circuit Decommission",
            intent="Steps to decommission a circuit",
            steps=[
                ProcedureStep(step_number=1, description="Notify carrier"),
                ProcedureStep(
                    step_number=2,
                    description="Remove config",
                    prerequisites=[1],
                    responsible="Network Ops",
                ),
            ],
            source_chunk="chunk-1",
        )
        assert len(proc.steps) == 2
        assert proc.steps[1].prerequisites == [1]


class TestExtractedTableSemantic:
    def test_creation(self):
        ts = ExtractedTableSemantic(
            table_name="circuits",
            description="Active circuit inventory",
            columns=[
                ColumnSemantic(
                    column_name="circuit_id",
                    description="Primary identifier",
                    is_key=True,
                ),
                ColumnSemantic(
                    column_name="bandwidth",
                    description="Circuit bandwidth in Mbps",
                ),
            ],
        )
        assert ts.columns[0].is_key is True
        assert ts.columns[1].is_key is False


class TestExtractionResult:
    def test_defaults_empty(self):
        r = ExtractionResult()
        assert r.entities == []
        assert r.concepts == []
        assert r.relations == []
        assert r.propositions == []
        assert r.procedure is None
        assert r.table_semantic is None


# ── Store models ──────────────────────────────────────


class TestKnowledgeStoreEntry:
    def test_creation(self):
        e = KnowledgeStoreEntry(
            chunk_id="c1",
            provider_id="p1",
            source_file="f.txt",
            doc_type="text",
            text="hello",
            embedding=[0.1] * 768,
            char_start=0,
            char_end=5,
        )
        assert len(e.embedding) == 768


class TestProceduralStoreEntry:
    def test_auto_uuid(self):
        e1 = ProceduralStoreEntry(
            provider_id="p1",
            name="Decom",
            intent="Decommission a circuit",
            steps_json="[]",
            embedding=[0.1] * 768,
        )
        e2 = ProceduralStoreEntry(
            provider_id="p1",
            name="Provision",
            intent="Provision a circuit",
            steps_json="[]",
            embedding=[0.2] * 768,
        )
        assert e1.procedure_id != e2.procedure_id


# ── Query models ──────────────────────────────────────


class TestQueryRequest:
    def test_defaults(self):
        q = QueryRequest(provider_id="p1", question="What is X?")
        assert q.top_k == 5
        assert q.graph_hops == 2

    def test_custom_params(self):
        q = QueryRequest(
            provider_id="p1", question="What?", top_k=10, graph_hops=3
        )
        assert q.top_k == 10


class TestQueryResponse:
    def test_full_response(self):
        r = QueryResponse(
            answer="The bandwidth is 100 Mbps.",
            graph_nodes=[
                GraphNode(
                    node_id="n1",
                    label="Entity",
                    properties={"name": "CID-44821"},
                    relevance=0.95,
                )
            ],
            chunks_used=["c1", "c2"],
            procedures=["Circuit Decommission"],
            provider_id="p1",
        )
        assert len(r.graph_nodes) == 1
        assert r.graph_nodes[0].relevance == 0.95
