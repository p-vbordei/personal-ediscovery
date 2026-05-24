# Architecture — personal-ediscovery

## Layers

```
┌──────────────────────────────────────────────────────────┐
│ CLI (Typer)   FastAPI   MCP stdio                        │
├──────────────────────────────────────────────────────────┤
│ Query service: bm25 + (optional) vector ANN              │
├──────────────────────────────────────────────────────────┤
│ Index service: chunk → embed → store                     │
├──────────────────────────────────────────────────────────┤
│ Source adapters: fs-text, fs-doc, mail, signal-export,   │
│ whatsapp-text, photos-exif                               │
├──────────────────────────────────────────────────────────┤
│ Storage: SQLite (BM25) + sqlite-vec (vectors, v0.2)      │
└──────────────────────────────────────────────────────────┘
```

## Storage

SQLite file at `~/.personal-ediscovery/store.sqlite`:

```sql
CREATE TABLE collections(
  name TEXT PRIMARY KEY,
  root TEXT NOT NULL,
  adapter TEXT NOT NULL,
  created_at TEXT NOT NULL,
  consent_token TEXT NOT NULL
);

CREATE TABLE documents(
  id TEXT PRIMARY KEY,
  collection TEXT NOT NULL,
  source_ref TEXT NOT NULL,   -- file path / message id / etc.
  title TEXT,
  modified_at TEXT,
  body TEXT NOT NULL,
  meta_json TEXT
);

CREATE TABLE tombstones(
  id TEXT NOT NULL,
  collection TEXT NOT NULL,
  removed_at TEXT NOT NULL,
  query TEXT
);

CREATE VIRTUAL TABLE documents_fts USING fts5(body, title, content='documents', content_rowid='rowid');
```

Vector ANN lives in `sqlite-vec` virtual table in v0.2.

## Adapter contract

```python
class SourceAdapter(Protocol):
    name: str
    def discover(self, root: Path) -> Iterator[SourceItem]: ...

class SourceItem(BaseModel):
    source_ref: str
    title: str | None
    modified_at: datetime | None
    body: str
    meta: dict[str, Any]
```

The MVP ships `fs-text`. Other adapters are bridges to existing parsers (e.g. `pdfminer.six` for PDFs).

## Search

Two paths:

1. **BM25** via SQLite FTS5 — always available, no model dependency.
2. **Vector ANN** via `sqlite-vec` + a local embedder — opt-in.

Default ranker blends both (RRF — reciprocal rank fusion) when both are available; falls back to BM25 alone otherwise.

## Privacy & consent

- Each `collections` row carries a `consent_token` set at `init` time.
- The MCP server requires the calling agent to present a *current-session consent grant* derived from this token before searches return.
- `forget` writes to `tombstones` and deletes from `documents` and `documents_fts`. Tombstones can be exported via [memory-portability](../memory-portability/) bundles.
- Network egress is off by default; the only listening sockets are localhost FastAPI + the MCP stdio process.

## MCP server (planned full integration)

Three tools:

- `ediscovery.list_collections() -> [{name, adapter, count}]`
- `ediscovery.search(query, collection?, k?) -> [{id, title, snippet, ref}]`
- `ediscovery.forget(query, collection?) -> {removed: int, tombstones: int}`

Each tool is registered via the [mcp-provenance](../mcp-provenance/) manifest with:

- `capabilities.network.noEgress: true`
- `capabilities.filesystem.read: [<configured roots>]`
- `capabilities.userApprovalRequiredFor: ["ediscovery.forget"]`

## Non-goals

- Not a screen recorder (no Rewind-style continuous capture).
- Not a cloud product.
- Not an HR / e-discovery legal tool — name is metaphorical.
