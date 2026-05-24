"""Service layer: index a collection, search across collections."""

from __future__ import annotations

from pathlib import Path

from .adapters import get_adapter
from .models import Document, Hit
from .store import Store


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
    # Truncate-and-reload so re-indexing the same source doesn't accumulate
    # duplicate rows. Tombstones are intentionally not recorded here (this is
    # an internal refresh, not a user-initiated forget).
    store.clear_collection(name)
    return store.add_documents(name, docs)


def search(store: Store, query: str, collection: str | None = None, k: int = 10) -> list[Hit]:
    raw = store.search_bm25(query, collection, k=k)
    out: list[Hit] = []
    for doc, score in raw:
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
