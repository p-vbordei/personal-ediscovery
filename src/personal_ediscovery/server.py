"""FastAPI server for personal-ediscovery."""

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .services import index_collection, search
from .store import Store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup
    app.state.store = Store()
    yield
    # Teardown
    app.state.store.db.close()

app = FastAPI(title="Personal e-Discovery API", lifespan=lifespan)

# Mount the web UI directory if it exists
web_dir = os.path.join(os.path.dirname(__file__), "web")
if os.path.exists(web_dir):
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    index_path = os.path.join(web_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Web UI not found</h1><p>Please place index.html in src/personal_ediscovery/web/</p>"

class CollectionCreate(BaseModel):
    name: str
    root: str
    adapter: str = "fs-text"

class ForgetRequest(BaseModel):
    collection: str
    query: str

@app.get("/api/collections")
def list_collections() -> list[dict[str, Any]]:
    store: Store = app.state.store
    cols = []
    for c in store.list_collections():
        cols.append({
            "name": c.name,
            "root": c.root,
            "adapter": c.adapter,
            "created_at": c.created_at.isoformat(),
            "doc_count": store.count_documents(c.name)
        })
    return cols

@app.post("/api/collections")
def create_collection(req: CollectionCreate) -> dict[str, Any]:
    store: Store = app.state.store
    if store.get_collection(req.name):
        raise HTTPException(status_code=400, detail=f"Collection '{req.name}' already exists.")
    col = store.create_collection(req.name, req.root, req.adapter)
    return {"status": "success", "name": col.name}

@app.post("/api/collections/{name}/index")
def index_collection_ep(name: str) -> dict[str, Any]:
    store: Store = app.state.store
    try:
        n = index_collection(store, name)
        return {"status": "success", "indexed": n}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/search")
def search_ep(q: str, collection: str | None = None, k: int = 10) -> list[dict[str, Any]]:
    store: Store = app.state.store
    hits = search(store, q, collection, k)
    return [h.model_dump(mode="json") for h in hits]

@app.post("/api/forget")
def forget_ep(req: ForgetRequest) -> dict[str, Any]:
    store: Store = app.state.store
    if not store.get_collection(req.collection):
        raise HTTPException(status_code=404, detail=f"Collection '{req.collection}' not found.")
    removed = store.forget(req.collection, req.query)
    return {"status": "success", "removed": removed}
