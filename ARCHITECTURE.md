# Architecture — personal-ediscovery

## Layers

```
┌──────────────────────────────────────────────────────────┐
│  CLI (Typer)     Web UI (HTML5/JS)   FastAPI Backend     │
├──────────────────────────────────────────────────────────┤
│  FastMCP Server (list, grant_consent, search, forget)    │
├──────────────────────────────────────────────────────────┤
│  Query Service: Hybrid search (BM25 + sqlite-vec ANN)    │
│  with Reciprocal Rank Fusion (RRF)                       │
├──────────────────────────────────────────────────────────┤
│  Index Service: Parse → Chunk → Embed                    │
├──────────────────────────────────────────────────────────┤
│  Source Adapters:                                        │
│  - fs-text (txt, md)                                     │
│  - fs-doc (pdf, docx, xlsx)                              │
│  - mail (eml, mbox)                                      │
│  - signal-export (json)                                  │
│  - whatsapp-text (txt block parsing)                     │
│  - photos-exif (PIL tags)                                │
├──────────────────────────────────────────────────────────┤
│  Storage: SQLite (WAL mode)                              │
│  - documents_fts (FTS5 virtual table for BM25)           │
│  - vec_documents (vec0 virtual table via sqlite-vec)     │
└──────────────────────────────────────────────────────────┘
```

---

## Storage & Schema

The storage layer resides in a single SQLite database file at `~/.personal-ediscovery/store.sqlite`. It uses WAL (Write-Ahead Logging) mode for concurrent access between the Web server, MCP server, and CLI commands.

### Table Schema

```sql
-- Collections configuration
CREATE TABLE collections(
  name TEXT PRIMARY KEY,
  root TEXT NOT NULL,
  adapter TEXT NOT NULL,
  created_at TEXT NOT NULL,
  consent_token TEXT NOT NULL
);

-- Main document body & metadata storage
CREATE TABLE documents(
  id TEXT PRIMARY KEY,
  collection TEXT NOT NULL,
  source_ref TEXT NOT NULL,   -- file path / message ID / line range
  title TEXT,
  modified_at TEXT,
  body TEXT NOT NULL,
  meta_json TEXT,
  FOREIGN KEY(collection) REFERENCES collections(name)
);

-- Full-Text Search (FTS5) for BM25
CREATE VIRTUAL TABLE documents_fts USING fts5(
  body, 
  title, 
  content='documents', 
  content_rowid='rowid'
);

-- Triggers to sync documents with FTS5 virtual table
CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
  INSERT INTO documents_fts(rowid, body, title) VALUES (new.rowid, new.body, new.title);
END;
CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN
  INSERT INTO documents_fts(documents_fts, rowid, body, title) VALUES('delete', old.rowid, old.body, old.title);
END;

-- Vector Storage (via sqlite-vec)
CREATE VIRTUAL TABLE vec_documents USING vec0(
  id TEXT PRIMARY KEY, 
  embedding float[384]
);

-- Tombstones for forgotten documents
CREATE TABLE tombstones(
  id TEXT NOT NULL,
  collection TEXT NOT NULL,
  removed_at TEXT NOT NULL,
  query TEXT
);
```

---

## Adapter Contract

All content source parsers must implement the `SourceAdapter` protocol:

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

### Registered Adapters:
1. **`fs-text`**: Processes local text files.
2. **`fs-doc`**: Leverages `pypdf`, `python-docx`, and `openpyxl` to extract plaintext from office files.
3. **`mail`**: Reads standard `.mbox` folders and individual `.eml` files using standard python `email` policies.
4. **`signal-export`**: Parses message chains from decrypted Signal JSON outputs.
5. **`whatsapp-text`**: Employs regex structures to chunk text transcripts into grouped conversation blocks.
6. **`photos-exif`**: Uses Pillow's `ExifTags` to index timestamp, model, and metadata information for directories of images.

---

## Search Pipeline

The search execution leverages a hybrid BM25 + Vector ANN matching framework:

1. **Keyword Match (BM25)**: SQLite FTS5 retrieves matching terms, scoring documents based on density and term frequency.
2. **Semantic Match (Vector ANN)**:
   - Uses `sentence-transformers` with the `all-MiniLM-L6-v2` model to embed the search query.
   - Queries `vec_documents` using `sqlite-vec` distance metrics.
   - Filters out poor matches (distance threshold `<= 1.2`).
3. **Reciprocal Rank Fusion (RRF)**:
   - Fuses rankings from both lists.
   - Formula: $Score(d) = \sum_{m \in M} \frac{1}{60 + Rank_m(d)}$
   - Sorts results descending by fused score to return the top `k` most relevant hits.

---

## Web Server API

The FastAPI server (`server.py`) exposes endpoints for administrative actions and frontend queries:
- **`GET /api/collections`**: Lists all collections, status, and document counts.
- **`POST /api/collections`**: Registers a new directory to be indexed.
- **`POST /api/collections/{name}/index`**: Triggers document discovery, text extraction, embedding generation, and DB insertion.
- **`GET /api/search?q=...&collection=...`**: Executes hybrid search query.
- **`POST /api/forget`**: Deletes items matching search terms from the collection database and writes a tombstone.

---

## MCP Server Design

The FastMCP server (`mcp_server.py`) exposes tools for LLM interaction:
- **`list_collections()`**: Shows available collections and whether they are locked or unlocked.
- **`grant_consent(collection, token)`**: Presents a token to unlock a collection for the current session.
- **`search(query, collection?, k?)`**: Performs search across unlocked collections.
- **`forget(collection, query)`**: Scrubs items matching query.

### Security Gating
To protect user privacy, collections start as **LOCKED** inside the MCP server. An LLM agent cannot retrieve content from any collection unless the user has provided the corresponding `consent_token` to the agent, which then unlocks access via the `grant_consent` tool for the duration of the current session.

---

## Privacy & Tombstones

- **No Remote Calls**: The embedding and database operations run entirely locally.
- **Forget Operations**: The `forget` tool performs actual deletions from the database. A record of deleted files is kept in the `tombstones` table so other local synchronization agents or exports can recognize the deletion boundary.
