import io
import logging
import tempfile
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument

from models import DocumentType, ParseResult

logger = logging.getLogger(__name__)

# ── Docling converter (light mode) ────────────────────

_converter: DocumentConverter | None = None


def _get_converter() -> DocumentConverter:
    """Singleton converter configured for speed — no OCR, fast table mode."""
    global _converter
    if _converter is None:
        pdf_options = PdfPipelineOptions(
            do_ocr=False,
            do_table_structure=True,
            table_structure_options=TableStructureOptions(
                mode=TableFormerMode.FAST,
            ),
        )
        _converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
            }
        )
    return _converter


def warm_up_converter() -> None:
    """Pre-initialize the Docling converter and its ML models at startup.

    The first PDF conversion triggers model loading (layout detection,
    table structure) which can take 30-60s on CPU.  Calling this at
    startup moves that cost out of the first user request.
    """
    logger.info("Warming up Docling PDF converter (loading ML models)...")
    _get_converter()
    logger.info("Docling converter ready")


# ── Format mapping ────────────────────────────────────

DOC_TYPE_TO_EXTENSION: dict[DocumentType, str] = {
    DocumentType.PDF: ".pdf",
    DocumentType.TEXT: ".md",  # Docling treats plain text as Markdown
    DocumentType.SOP: ".md",
    DocumentType.CSV: ".csv",
    DocumentType.DDL: ".md",  # DDL is plain text, use Markdown path
}


# ── Parsing functions ─────────────────────────────────


def _convert_bytes(
    content: bytes, filename: str, doc_type: DocumentType
) -> DoclingDocument:
    """Write content to a temp file and convert via Docling."""
    converter = _get_converter()
    ext = DOC_TYPE_TO_EXTENSION.get(doc_type, ".md")

    # For text-like formats, use convert_string (faster, no temp file)
    if doc_type in (DocumentType.TEXT, DocumentType.SOP, DocumentType.DDL):
        text = content.decode("utf-8")
        result = converter.convert_string(
            content=text,
            format=InputFormat.MD,
            name=filename,
        )
        return result.document

    # For binary formats (PDF) and CSV, write to temp file
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        tmp_path = Path(tmp.name)

    try:
        result = converter.convert(str(tmp_path))
        return result.document
    finally:
        tmp_path.unlink(missing_ok=True)


def parse_document(
    content: bytes, filename: str, doc_type: DocumentType
) -> ParseResult:
    """Parse any supported document type via Docling and return a ParseResult."""
    doc = _convert_bytes(content, filename, doc_type)

    # Export full text — Docling preserves structure in Markdown
    text = doc.export_to_markdown()

    # Build metadata from the Docling document
    metadata: dict = {"filename": filename}

    if doc_type == DocumentType.PDF:
        metadata["page_count"] = doc.num_pages() if hasattr(doc, "num_pages") else 0
    elif doc_type == DocumentType.CSV:
        metadata["row_count"] = text.count("\n")

    metadata["char_count"] = len(text)

    logger.info(
        f"Parsed {filename} ({doc_type.value}) — {metadata.get('char_count', 0)} chars"
    )

    return ParseResult(
        text=text,
        metadata=metadata,
        doc_type=doc_type,
        docling_document=doc,
    )
