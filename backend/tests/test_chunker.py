import pytest

from models import DocumentType, KnowledgeChunk, ParseResult
from ingestion.chunker import _chunk_text_fallback, chunk_document


class TestTextFallbackChunker:
    """Test the fallback sliding-window chunker."""

    def test_empty_text(self):
        chunks = _chunk_text_fallback("", "p1", "f.txt", DocumentType.TEXT)
        assert chunks == []

    def test_whitespace_only(self):
        chunks = _chunk_text_fallback("   \n\n  ", "p1", "f.txt", DocumentType.TEXT)
        assert chunks == []

    def test_short_text_single_chunk(self):
        text = "Hello world"
        chunks = _chunk_text_fallback(text, "p1", "f.txt", DocumentType.TEXT)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].char_start == 0
        assert chunks[0].char_end == len(text)

    def test_chunk_ids_unique(self):
        text = "a" * 2000
        chunks = _chunk_text_fallback(text, "p1", "f.txt", DocumentType.TEXT)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_provider_and_source_propagated(self):
        chunks = _chunk_text_fallback("Hello", "my-provider", "doc.pdf", DocumentType.PDF)
        assert all(c.provider_id == "my-provider" for c in chunks)
        assert all(c.source_file == "doc.pdf" for c in chunks)


class TestChunkDocumentFallback:
    """Test chunk_document falls back when no DoclingDocument is present."""

    def test_fallback_when_no_docling_doc(self):
        pr = ParseResult(
            text="Some text content here for chunking.",
            metadata={"filename": "test.txt"},
            doc_type=DocumentType.TEXT,
            docling_document=None,
        )
        chunks = chunk_document(pr, "p1", "test.txt")
        assert len(chunks) >= 1
        assert all(isinstance(c, KnowledgeChunk) for c in chunks)


class TestChunkDocumentWithDocling:
    """Test chunk_document with a real Docling document (integration-ish)."""

    def test_text_document_chunking(self):
        from ingestion.parsers import parse_document

        content = b"# Introduction\n\nThis is a test document about circuits.\n\n## Details\n\nCircuit CID-44821 terminates at LON-CE-01."
        pr = parse_document(content, "test.md", DocumentType.TEXT)
        assert pr.docling_document is not None

        chunks = chunk_document(pr, "test-provider", "test.md")
        assert len(chunks) >= 1
        assert all(c.provider_id == "test-provider" for c in chunks)
        assert all(c.source_file == "test.md" for c in chunks)
        # Docling contextualize() should include heading context
        assert any(len(c.text) > 0 for c in chunks)
