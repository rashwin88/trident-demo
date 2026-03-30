import pytest

from models import DocumentType, ParseResult


class TestParseResult:
    def test_creation_with_docling_doc(self):
        pr = ParseResult(
            text="# Hello\n\nSome content",
            metadata={"filename": "test.md", "char_count": 21},
            doc_type=DocumentType.TEXT,
            docling_document="mock_doc",  # Any type allowed
        )
        assert pr.docling_document == "mock_doc"

    def test_creation_without_docling_doc(self):
        pr = ParseResult(
            text="hello",
            metadata={"filename": "test.txt"},
            doc_type=DocumentType.TEXT,
        )
        assert pr.docling_document is None

    def test_doc_type_mapping(self):
        from ingestion.parsers import DOC_TYPE_TO_EXTENSION

        assert DOC_TYPE_TO_EXTENSION[DocumentType.PDF] == ".pdf"
        assert DOC_TYPE_TO_EXTENSION[DocumentType.TEXT] == ".md"
        assert DOC_TYPE_TO_EXTENSION[DocumentType.SOP] == ".md"
        assert DOC_TYPE_TO_EXTENSION[DocumentType.CSV] == ".csv"
        assert DOC_TYPE_TO_EXTENSION[DocumentType.DDL] == ".md"


class TestParseDocumentTextTypes:
    """Test that text-based document types go through Docling's convert_string."""

    def test_parse_text(self):
        from ingestion.parsers import parse_document

        content = b"This is a plain text document.\nWith multiple lines."
        result = parse_document(content, "test.txt", DocumentType.TEXT)
        assert isinstance(result, ParseResult)
        assert result.doc_type == DocumentType.TEXT
        assert result.docling_document is not None
        assert len(result.text) > 0

    def test_parse_sop(self):
        from ingestion.parsers import parse_document

        content = b"# SOP: Circuit Decommission\n\n1. Notify carrier\n2. Remove config"
        result = parse_document(content, "decom.sop", DocumentType.SOP)
        assert result.doc_type == DocumentType.SOP
        assert result.docling_document is not None

    def test_parse_ddl(self):
        from ingestion.parsers import parse_document

        content = b"CREATE TABLE circuits (\n  circuit_id VARCHAR(64) PRIMARY KEY\n);"
        result = parse_document(content, "schema.sql", DocumentType.DDL)
        assert result.doc_type == DocumentType.DDL
        assert result.docling_document is not None

    def test_empty_text(self):
        from ingestion.parsers import parse_document

        content = b""
        result = parse_document(content, "empty.txt", DocumentType.TEXT)
        assert isinstance(result, ParseResult)
