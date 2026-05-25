"""Service layer: index a collection, search across collections."""

from __future__ import annotations

import logging
from pathlib import Path

from .adapters import get_adapter
from .embedding import EmbeddingService
from .models import Document, Hit
from .store import Store

logger = logging.getLogger(__name__)

# The constant k used in Reciprocal Rank Fusion (RRF)
RRF_K = 60


def index_collection(store: Store, name: str) -> int:
    col = store.get_collection(name)
    if not col:
        raise KeyError(f"Unknown collection: {name}")
    
    adapter = get_adapter(col.adapter)
    items = list(adapter.discover(Path(col.root)))
    
    docs = [
        Document(
            collection=name,
            source_ref=i.source_ref,
            title=i.title,
            modified_at=i.modified_at,
            body=i.body,
            meta=i.meta,
        )
        for i in items
    ]

    embedder = EmbeddingService.load() if store.vec_enabled else None
    embeddings = None
    if embedder is not None:
        logger.info("Generating embeddings for %d documents in %s...", len(docs), name)
        # Embed the concatenation of title and body
        texts_to_embed = [f"{d.title or ''}\n{d.body}" for d in docs]
        embeddings = embedder.embed(texts_to_embed)

    # Truncate-and-reload so re-indexing the same source doesn't accumulate
    # duplicate rows. Tombstones are intentionally not recorded here.
    store.clear_collection(name)
    return store.add_documents(name, docs, embeddings)


def search(store: Store, query: str, collection: str | None = None, k: int = 10) -> list[Hit]:
    # 1. Fetch BM25 results
    bm25_raw = store.search_bm25(query, collection, k=k * 2)
    bm25_ranks = {doc.id: rank for rank, (doc, _) in enumerate(bm25_raw, start=1)}
    bm25_docs = {doc.id: doc for doc, _ in bm25_raw}

    # 2. Fetch Vector results (if available)
    vec_ranks = {}
    vec_docs = {}
    if store.vec_enabled:
        embedder = EmbeddingService.load()
        if embedder:
            query_emb = embedder.embed_query(query)
            vec_raw = store.search_vector(query_emb, collection, k=k * 2)
            filtered_vec = [(doc, dist) for doc, dist in vec_raw if dist <= 1.2]
            vec_ranks = {doc.id: rank for rank, (doc, _) in enumerate(filtered_vec, start=1)}
            vec_docs = {doc.id: doc for doc, _ in filtered_vec}

    # 3. Fuse scores (Reciprocal Rank Fusion)
    all_ids = set(bm25_ranks.keys()) | set(vec_ranks.keys())
    
    fused_scores = {}
    for did in all_ids:
        score = 0.0
        if did in bm25_ranks:
            score += 1.0 / (RRF_K + bm25_ranks[did])
        if did in vec_ranks:
            score += 1.0 / (RRF_K + vec_ranks[did])
        fused_scores[did] = score

    # Sort descending by fused score
    sorted_ids = sorted(fused_scores.keys(), key=lambda did: fused_scores[did], reverse=True)
    top_ids = sorted_ids[:k]

    out: list[Hit] = []
    for did in top_ids:
        doc = bm25_docs.get(did) or vec_docs[did]
        score = fused_scores[did]
        snippet = make_snippet(doc.body, query)
        out.append(
            Hit(
                id=doc.id,
                collection=doc.collection,
                title=doc.title,
                snippet=snippet,
                source_ref=doc.source_ref,
                score=score,
            )
        )
    return out


def make_snippet(body: str, query: str, radius: int = 80) -> str:
    needle = query.lower()
    hay = body.lower()
    idx = hay.find(needle)
    if idx < 0:
        return body[: 2 * radius] + ("…" if len(body) > 2 * radius else "")
    start = max(0, idx - radius)
    end = min(len(body), idx + len(needle) + radius)
    out = body[start:end]
    if start > 0:
        out = "…" + out
    if end < len(body):
        out = out + "…"
    return out.replace("\n", " ").strip()
