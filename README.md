# personal-ediscovery

> A privacy-first, local agent that indexes *your* digital life — emails, chats, photos, documents — and exposes it to a personal AI assistant via MCP. No cloud, no embedding leaks.

## Problem

Closed products (Rewind.ai, Limitless, Microsoft Recall) increasingly index your screen, audio, or files into a cloud-hosted personal index. The win is real — "remember every meeting, every doc, every conversation." The cost is real too: the most sensitive corpus you have, in someone else's data center.

The **privacy-first, fully-local, open-source** version of this category is **missing** as of mid-2026:

- Apple's on-device search is closed, indexes only Apple-managed corpora, and isn't agent-addressable.
- Spotlight, Recoll, DocFetcher are pre-AI; no semantic search, no agent interface.
- LlamaIndex and LangChain provide *libraries* but not a turnkey product the way Rewind is.

## Why doesn't this already exist

- Indexing personal data correctly (chat exports, EXIF, MBOX, OFFICE) is unglamorous engineering.
- Local embeddings are now cheap enough (CLIP, all-MiniLM, BGE small) but require GPU or modern Apple Silicon for reasonable performance.
- Agent interfaces (MCP) only became standardized in late 2024.

The pieces exist; the product doesn't.

## What this is

A Python service that:

1. **Indexes** local folders/mailboxes/exports into a SQLite + sqlite-vec store.
2. **Embeds** using a local model (default `all-MiniLM-L6-v2` via `sentence-transformers`).
3. **Serves** search via a CLI, a FastAPI endpoint, and an **MCP server** so Claude Desktop / Cursor / any MCP-aware agent can query it.
4. **Respects consent**: every index is opt-in and per-collection; tombstone format makes "forget this" a first-class operation; nothing ever leaves the device by default.

## Supported sources (MVP)

| Source | Adapter |
|---|---|
| Local folder of text/markdown | `fs-text` |
| PDF / Word / Excel | `fs-doc` (via `unstructured` or `pdfminer` + lightweight parsers) |
| Email (MBOX, EML) | `mail` |
| Signal export (JSON) | `signal-export` |
| WhatsApp chat export (TXT) | `whatsapp-text` |
| Photo folder (with EXIF) | `photos-exif` |

Planned: Slack export, Discord export, Telegram export, browser-history bookmarks.

## Quick start

```bash
uv venv
uv pip install -e .

# Initialize a collection
ediscovery init --collection notes --root ~/Documents/Notes --adapter fs-text

# Index it
ediscovery index --collection notes

# Search
ediscovery search "kitchen renovation budget"

# Forget anything matching a query
ediscovery forget --collection notes --query "old roommate"

# Serve over MCP stdio for an agent
ediscovery mcp-stdio
```

## MVP scope

- [x] SQLite + (planned) `sqlite-vec` storage
- [x] `fs-text` adapter (txt, md)
- [x] Collection management (add / list / remove / re-index)
- [x] CLI (`init`, `index`, `search`, `forget`, `mcp-stdio`)
- [x] FastAPI endpoint
- [x] Stub MCP-stdio process so the contract is visible (real MCP wiring is v0.2)
- [x] Local embedding via `sentence-transformers` (optional dependency)
- [x] Unit tests on the BM25 fallback path (so tests run without the embedding model)
- [ ] PDF / Word / Excel adapters
- [ ] MBOX / Signal / WhatsApp / Photos adapters
- [ ] `sqlite-vec` for ANN; current MVP uses brute-force cosine in Python
- [ ] Real MCP server using the official Python SDK
- [ ] Web UI

## Privacy posture

- **Default-off network egress.** No telemetry. The default install does not call out.
- **Per-collection consent.** Each collection has an explicit consent token at creation; the MCP server refuses queries until the user has granted access for the current agent session.
- **Forget is first-class.** `forget` writes tombstones (using the [memory-portability](../memory-portability/) bundle format) and deletes index rows.
- **No streaming of bodies** through MCP without an explicit user consent for that query class.

## Roadmap

| Milestone | What |
|---|---|
| v0.1 | `fs-text` + CLI + FastAPI + stub MCP + BM25 fallback |
| v0.2 | `sentence-transformers` + `sqlite-vec` + real MCP server |
| v0.3 | PDF / Word / Excel / MBOX adapters |
| v0.4 | Signal / WhatsApp / Slack / Discord chat export adapters |
| v0.5 | Photos w/ CLIP, Web UI, multi-collection search ranking |

## References

- Research paper §10.2 #28
- [memory-portability](../memory-portability/) — used for forget tombstones

## License

Apache-2.0 © Vlad Bordei
