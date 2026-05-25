"""CLI for personal-ediscovery."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn

from .services import index_collection, search
from .store import Store

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _store() -> Store:
    return Store()


@app.command()
def init(
    collection: str = typer.Option(..., "--collection"),
    root: Path = typer.Option(..., "--root", file_okay=False, dir_okay=True, resolve_path=True),
    adapter: str = typer.Option("fs-text", "--adapter"),
) -> None:
    """Create a new collection rooted at a folder."""
    store = _store()
    if store.get_collection(collection):
        typer.echo(f"Collection {collection} already exists.")
        raise typer.Exit(code=1)
    col = store.create_collection(collection, str(root), adapter)
    typer.echo(f"Created collection: {col.name} (root={col.root}, adapter={col.adapter})")
    typer.echo(f"Consent token: {col.consent_token}")


@app.command()
def index(collection: str = typer.Option(..., "--collection")) -> None:
    """Index all documents in a collection."""
    n = index_collection(_store(), collection)
    typer.echo(f"Indexed {n} documents into {collection}.")


@app.command(name="list")
def list_cmd() -> None:
    """List collections."""
    s = _store()
    for c in s.list_collections():
        typer.echo(f"{c.name:20s} {c.adapter:10s} {c.root}   ({s.count_documents(c.name)} docs)")


@app.command(name="search")
def search_cmd(
    query: str = typer.Argument(...),
    collection: str | None = typer.Option(None, "--collection"),
    k: int = typer.Option(10, "--k"),
    output: str = typer.Option("text", "--output", help="text|json"),
) -> None:
    """Search across one or all collections."""
    hits = search(_store(), query, collection, k)
    if output == "json":
        typer.echo(json.dumps([h.model_dump(mode="json") for h in hits], indent=2))
        return
    for h in hits:
        typer.echo(f"[{h.score:7.3f}] {h.collection}/{h.title or '(no title)'}")
        typer.echo(f"           {h.snippet}")
        typer.echo(f"           {h.source_ref}")


@app.command()
def forget(
    collection: str = typer.Option(..., "--collection"),
    query: str = typer.Option(..., "--query"),
) -> None:
    """Delete documents matching `query` from a collection (creates tombstones)."""
    n = _store().forget(collection, query)
    typer.echo(f"Removed {n} document(s).")


@app.command(name="mcp-stdio")
def mcp_stdio() -> None:
    """Run the real MCP-over-stdio process using FastMCP."""
    from .mcp_server import mcp
    mcp.run()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Run the FastAPI server and Web UI."""
    typer.echo(f"Starting server at http://{host}:{port}")
    uvicorn.run("personal_ediscovery.server:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
