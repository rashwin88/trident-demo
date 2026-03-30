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
    """Singleton HybridChunker — token-aware, structure-aware chunking."""
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
    """Chunk a parsed document using Docling's HybridChunker.

    Falls back to simple text splitting if no DoclingDocument is available.
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
    """Use Docling's HybridChunker for structure-aware, token-aware chunking."""
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
    """Fallback: character-level sliding window with overlap."""
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
