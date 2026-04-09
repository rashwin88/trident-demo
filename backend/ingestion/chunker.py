"""Document chunking module — splits parsed documents into embedding-ready chunks.

Takes a ParseResult (produced by ingestion.parsers) and splits it into a list
of KnowledgeChunk objects suitable for embedding and graph extraction.

Primary strategy: Docling's HybridChunker, which is both token-aware (respects
the embedding model's context window) and structure-aware (splits along heading
and section boundaries rather than mid-sentence).

Fallback strategy: A simple character-level sliding window with overlap, used
only when no DoclingDocument is available (e.g., if a future parser bypasses
Docling).

Consumed by:
    - ingestion.pipeline  (calls chunk_document as the second pipeline stage)

Key design choices:
    - Singleton chunker avoids re-creating the tokenizer on every call.
    - contextualize() is called on each chunk to prepend heading breadcrumbs,
      which dramatically improves embedding quality for out-of-context chunks.
    - Chunk size and overlap are driven by config.settings.
"""

import logging
from uuid import uuid4

import tiktoken
from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.types.doc import DoclingDocument

from config import settings
from models import DocumentType, KnowledgeChunk, ParseResult

logger = logging.getLogger(__name__)

# ── Docling HybridChunker (singleton) ─────────────────

_chunker: HybridChunker | None = None


def _get_chunker() -> HybridChunker:
    """Return the singleton HybridChunker, creating it on first call.

    Uses OpenAI's cl100k_base tokenizer so token counts match the embedding
    model. merge_peers=True allows adjacent small sections to be combined
    into a single chunk, reducing the total number of embeddings.

    Returns:
        HybridChunker: A reusable chunker instance.
    """
    global _chunker
    if _chunker is None:
        tokenizer = OpenAITokenizer(
            tokenizer=tiktoken.get_encoding("cl100k_base"),
            max_tokens=settings.CHUNK_SIZE,
        )
        _chunker = HybridChunker(
            tokenizer=tokenizer,
            merge_peers=True,
        )
    return _chunker


def chunk_document(
    parse_result: ParseResult,
    provider_id: str,
    source_file: str,
) -> list[KnowledgeChunk]:
    """Chunk a parsed document into KnowledgeChunk objects.

    Prefers Docling's HybridChunker for structure-aware splitting.  Falls back
    to a simple character sliding window if no DoclingDocument is available.

    Args:
        parse_result: Output of parse_document, containing text and the
                      optional DoclingDocument.
        provider_id:  ID of the data-provider that owns this document.
        source_file:  Original filename, attached to each chunk for tracing.

    Returns:
        List of KnowledgeChunk objects ready for embedding and extraction.
    """
    doc = parse_result.docling_document
    chunker = _get_chunker()

    if doc is not None:
        return _chunk_with_docling(doc, chunker, provider_id, source_file, parse_result.doc_type)

    # Fallback: plain sliding window (shouldn't happen with Docling parser)
    logger.warning(f"No DoclingDocument for {source_file}, falling back to text chunking")
    return _chunk_text_fallback(
        parse_result.text, provider_id, source_file, parse_result.doc_type
    )


def _chunk_with_docling(
    doc: DoclingDocument,
    chunker: HybridChunker,
    provider_id: str,
    source_file: str,
    doc_type: DocumentType,
) -> list[KnowledgeChunk]:
    """Split a DoclingDocument using HybridChunker.

    Each raw chunk is passed through contextualize() which prepends the
    heading hierarchy (e.g. "Chapter 3 > Section 3.2 > ...") so the chunk
    text is self-contained when embedded in isolation.

    Args:
        doc:         The parsed DoclingDocument with structural annotations.
        chunker:     Singleton HybridChunker instance.
        provider_id: Data-provider ID attached to each chunk.
        source_file: Original filename for provenance tracking.
        doc_type:    Document type enum, carried through to the chunk model.

    Returns:
        List of KnowledgeChunk objects (empty chunks are filtered out).
    """
    docling_chunks = list(chunker.chunk(doc))
    knowledge_chunks: list[KnowledgeChunk] = []

    for chunk in docling_chunks:
        # contextualize() prepends heading context for better embeddings
        text = chunker.contextualize(chunk)

        if not text.strip():
            continue

        knowledge_chunks.append(
            KnowledgeChunk(
                chunk_id=str(uuid4()),
                provider_id=provider_id,
                source_file=source_file,
                doc_type=doc_type,
                text=text,
                char_start=0,  # Docling chunks don't track char offsets
                char_end=len(text),
            )
        )

    logger.info(
        f"Chunked {source_file} into {len(knowledge_chunks)} chunks via Docling HybridChunker"
    )
    return knowledge_chunks


def _chunk_text_fallback(
    text: str,
    provider_id: str,
    source_file: str,
    doc_type: DocumentType,
) -> list[KnowledgeChunk]:
    """Fallback chunker: character-level sliding window with overlap.

    Used only when a DoclingDocument is unavailable.  Unlike HybridChunker
    this has no awareness of document structure, so chunk boundaries may
    land mid-sentence.  The overlap region helps downstream embeddings
    retain cross-boundary context.

    Args:
        text:        Full document text to split.
        provider_id: Data-provider ID attached to each chunk.
        source_file: Original filename for provenance tracking.
        doc_type:    Document type enum, carried through to the chunk model.

    Returns:
        List of KnowledgeChunk objects with accurate char_start/char_end offsets.
    """
    size = settings.CHUNK_SIZE
    overlap = settings.CHUNK_OVERLAP

    if not text.strip():
        return []

    chunks: list[KnowledgeChunk] = []
    start = 0

    while start < len(text):
        end = min(start + size, len(text))
        chunk_text = text[start:end]

        if chunk_text.strip():
            chunks.append(
                KnowledgeChunk(
                    provider_id=provider_id,
                    source_file=source_file,
                    doc_type=doc_type,
                    text=chunk_text,
                    char_start=start,
                    char_end=end,
                )
            )

        if end >= len(text):
            break
        start += size - overlap

    return chunks
