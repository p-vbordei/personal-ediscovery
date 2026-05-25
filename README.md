# personal-ediscovery

> A privacy-first, local agent that indexes *your* digital life — emails, chats, photos, documents — and exposes it to a personal AI assistant via Model Context Protocol (MCP). No cloud, no embedding leaks, completely local.

---

## Why Personal e-Discovery?

Many closed products index your screen, audio, or files to a cloud-hosted personal index. The value is real — "remember every meeting, document, and conversation." The cost is also real: your most sensitive data is stored on someone else's servers.

This project is a **privacy-first, fully-local, open-source** solution:
- **Local-first**: Runs completely on your device. Local embeddings, local storage, local processing.
- **Hybrid Search**: Fuses precise keyword search (BM25) with semantic vector search (ANN) using SQLite.
- **Agentic**: Integrates with Model Context Protocol (MCP) so tools like Claude Desktop, Cursor, or any MCP-compatible assistant can safely interact with your personal history.
- **Granular Consent**: All collections are gated behind session-based consent tokens. Agents cannot read your files without explicit approval.

---

## Features

### 1. Multi-Format Source Adapters
We support parsing and indexing a variety of personal formats natively:
- 📝 **`fs-text`**: Text and Markdown documents (`.txt`, `.md`, `.markdown`, `.text`).
- 📄 **`fs-doc`**: PDF (`pypdf`), Word (`python-docx`), and Excel (`openpyxl`) documents.
- ✉️ **`mail`**: Email Archives (`.eml` and `.mbox` files).
- 💬 **`signal-export`**: JSON thread exports from Signal.
- 🟢 **`whatsapp-text`**: Text-based exported WhatsApp conversations (intelligently groups message blocks).
- 📸 **`photos-exif`**: Image folders (JPEG, PNG, HEIC, etc.) indexing metadata such as Camera Model, Timestamp, and GPS coordinates.

### 2. Hybrid BM25 & Semantic Vector Search
- Powered by `sqlite-vec` (for native SQLite vector similarity search) and `sqlite` FTS5 (for full-text keyword indexing).
- Local embeddings generated via the `all-MiniLM-L6-v2` transformer model (384 dimensions).
- Uses **Reciprocal Rank Fusion (RRF)** to combine structural keywords and semantic intent into a single unified search ranking.

### 3. Glassmorphic Web UI
- Built with a premium, responsive glassmorphic dark UI.
- Manage collections, trigger re-indexing, search across all collections or filter by specific ones, and request hard deletions.
- Run `ediscovery serve` and open `http://localhost:8000`.

### 4. Consent-Gated FastMCP Server
- Provides a Model Context Protocol (MCP) endpoint over stdio.
- Every collection generates a unique **consent token** upon initialization.
- The MCP server defaults to `LOCKED` status for all collections. The connecting agent must use the `grant_consent` tool with the appropriate token to unlock a collection for the session.

---

## Installation

This project is built using Python and managed via `uv` for lightning-fast setup.

```bash
# Clone the repository
git clone https://github.com/p-vbordei/personal-ediscovery.git
cd personal-ediscovery

# Create a virtual environment and install dependencies
uv venv
uv pip install -e .
```

*Note: Optional parsing libraries (like `pypdf`, `python-docx`, `openpyxl`, `Pillow`) will be loaded automatically if present in the environment.*

---

## Quick Start

### 1. Initialize a Collection
Create a collection pointing to a local directory. This will output a unique consent token:
```bash
ediscovery init --collection my-notes --root ~/Documents/Notes --adapter fs-text
```

### 2. Index the Collection
Extract, chunk, and embed documents locally:
```bash
ediscovery index --collection my-notes
```

### 3. Search via CLI
Query the index using hybrid search:
```bash
ediscovery search "project launch deadline"
```
Or get clean JSON output:
```bash
ediscovery search "budget calculation" --output json
```

### 4. View Available Collections
```bash
ediscovery list
```

### 5. Start the Web UI
Launch the server:
```bash
ediscovery serve
```
Then visit `http://127.0.0.1:8000` to use the premium glassmorphic interface.

### 6. Forget / Tombstones
To permanently delete documents matching a query and record a cryptographic tombstone:
```bash
ediscovery forget --collection my-notes --query "draft contract"
```

---

## Agent Integration (MCP)

To hook up your personal search index to Cursor or Claude Desktop, register the CLI command as an MCP server:

### Connection Settings
- **Transport**: `stdio`
- **Command**: `uv`
- **Arguments**: `run`, `--project`, `/path/to/personal-ediscovery`, `ediscovery`, `mcp-stdio`

### Consent Flow
1. When the agent starts, it can call `list_collections()`. The agent will see the collections but they will be marked as `LOCKED (Requires consent token)`.
2. Provide the agent with the collection's consent token (generated during `init` or found in the DB).
3. The agent calls `grant_consent(collection="my-notes", token="<token>")`.
4. Once unlocked, the agent can call `search()` or `forget()` on that collection.

---

## Privacy Posture
- **Zero Telemetry**: We do not collect analytics, logs, or search queries.
- **Local Vectors**: Embeddings are generated on your CPU or local GPU/Apple Silicon neural engine.
- **Data Deletion**: The `forget` command deletes rows from FTS5 and the vector index, writing a cryptographic tombstone for tracking compliance.

---

## License
Apache-2.0 © Vlad Bordei
