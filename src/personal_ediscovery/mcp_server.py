"""FastMCP Server for personal-ediscovery."""

import json
from mcp.server.fastmcp import FastMCP
from .services import search as do_search
from .store import Store

# In-memory set of granted collections for the current session
_granted_collections: set[str] = set()

# Initialize the store globally for the MCP server
store = Store()

mcp = FastMCP("Personal E-Discovery", dependencies=["mcp", "pydantic"])


@mcp.tool()
def list_collections() -> str:
    """List all available collections in personal-ediscovery."""
    cols = store.list_collections()
    if not cols:
        return "No collections found."
    
    out = ["Available Collections:"]
    for c in cols:
        status = "UNLOCKED" if c.name in _granted_collections else "LOCKED (Requires consent token)"
        count = store.count_documents(c.name)
        out.append(f"- {c.name} (Adapter: {c.adapter}, Docs: {count}) [{status}]")
    
    return "\n".join(out)


@mcp.tool()
def grant_consent(collection: str, token: str) -> str:
    """Present a consent token to unlock a collection for the current session."""
    col = store.get_collection(collection)
    if not col:
        return f"Error: Collection '{collection}' not found."
    
    if col.consent_token == token:
        _granted_collections.add(collection)
        return f"Success: Consent granted. Collection '{collection}' is now unlocked for this session."
    
    return f"Error: Invalid consent token for collection '{collection}'."


@mcp.tool()
def search(query: str, collection: str | None = None, k: int = 10) -> str:
    """Search documents across one or all unlocked collections."""
    cols_to_search = []
    if collection:
        if collection not in _granted_collections:
            return (f"Error: Collection '{collection}' is locked. "
                    f"Please provide the consent token using the grant_consent tool.")
        cols_to_search = [collection]
    else:
        cols_to_search = list(_granted_collections)
        if not cols_to_search:
            return ("Error: All collections are currently locked. "
                    "Please provide a consent token using the grant_consent tool to search.")

    all_hits = []
    for col in cols_to_search:
        hits = do_search(store, query, col, k)
        all_hits.extend(hits)
    
    # Sort and take top k globally
    all_hits.sort(key=lambda h: h.score, reverse=True)
    top_hits = all_hits[:k]

    if not top_hits:
        return "No results found."

    out = [f"Found {len(top_hits)} results:"]
    for i, h in enumerate(top_hits, 1):
        out.append(f"\n{i}. [{h.collection}] {h.title or '(no title)'} (Score: {h.score:.3f})")
        out.append(f"   Ref: {h.source_ref}")
        out.append(f"   Snippet: {h.snippet}")

    return "\n".join(out)


@mcp.tool()
def forget(collection: str, query: str) -> str:
    """Delete documents matching a query from an unlocked collection (creates tombstones)."""
    if collection not in _granted_collections:
        return (f"Error: Collection '{collection}' is locked. "
                f"Please provide the consent token using the grant_consent tool.")
    
    removed = store.forget(collection, query)
    return f"Removed {removed} document(s) matching '{query}' from '{collection}'."

if __name__ == "__main__":
    mcp.run()
