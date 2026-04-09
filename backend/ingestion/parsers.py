"""Document parsing module — converts raw file bytes into structured text.

Uses Docling in light mode (no OCR, fast table detection) to parse PDFs,
HTML, CSV, plain-text, and Markdown documents into a unified DoclingDocument
representation. The DoclingDocument is passed downstream to the chunker,
which relies on its structural annotations for high-quality splitting.

Consumed by:
    - ingestion.pipeline  (calls parse_document as the first pipeline stage)
    - ingestion.chunker   (receives the DoclingDocument inside ParseResult)

Key design choices:
    - Singleton converter avoids repeated ML-model loading (~30-60s on CPU).
    - Text-like formats use convert_string (no temp file I/O).
    - Binary formats (PDF, CSV) are written to a temp file that is cleaned up
      immediately after conversion.
"""

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
    """Return the singleton Docling DocumentConverter, creating it on first call.

    Configured for speed over accuracy: OCR is disabled and table structure
    detection uses FAST mode. Only PDF-specific pipeline options are set;
    other formats (HTML, Markdown, CSV) use Docling defaults.

    Returns:
        DocumentConverter: A reusable converter instance.
    """
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

    Called by:
        main.py lifespan hook, so the latency is absorbed during server boot.
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
    DocumentType.WEB: ".html",
}


# ── Parsing functions ─────────────────────────────────


def _convert_bytes(
    content: bytes, filename: str, doc_type: DocumentType
) -> DoclingDocument:
    """Convert raw file bytes into a DoclingDocument.

    Routes to the most efficient Docling entry-point for each format:
    - Text/SOP/DDL  -> convert_string (Markdown mode, no disk I/O)
    - WEB (HTML)    -> convert_string (HTML mode)
    - PDF / CSV     -> temp file on disk, then convert()

    Args:
        content:  Raw bytes of the uploaded file.
        filename: Original filename (used as a label inside Docling).
        doc_type: Enum that determines which conversion path to take.

    Returns:
        DoclingDocument with structural annotations preserved.
    """
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

    # For HTML (web pages), use convert_string with HTML format
    if doc_type == DocumentType.WEB:
        html = content.decode("utf-8")
        result = converter.convert_string(
            content=html,
            format=InputFormat.HTML,
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
    """Parse any supported document type via Docling and return a ParseResult.

    This is the public entry-point for the parsing stage.  It converts the raw
    bytes, exports the full text as Markdown, and attaches format-specific
    metadata (page count for PDFs, row count for CSVs, etc.).

    Args:
        content:  Raw bytes of the uploaded file.
        filename: Original filename, carried through to metadata.
        doc_type: Document type enum used to select the conversion strategy.

    Returns:
        ParseResult containing the extracted text, metadata dict, doc_type,
        and the underlying DoclingDocument (used by the chunker).
    """
    doc = _convert_bytes(content, filename, doc_type)

    # Export full text — Docling preserves structure in Markdown
    text = doc.export_to_markdown()

    # Build metadata from the Docling document
    metadata: dict = {"filename": filename}

    if doc_type == DocumentType.PDF:
        metadata["page_count"] = doc.num_pages() if hasattr(doc, "num_pages") else 0
    elif doc_type == DocumentType.CSV:
        metadata["row_count"] = text.count("\n")
    elif doc_type == DocumentType.WEB:
        metadata["source_type"] = "web"

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
