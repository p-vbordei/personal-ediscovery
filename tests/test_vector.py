"""Tests for vector database functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_ediscovery.embedding import EmbeddingService
from personal_ediscovery.services import index_collection, search
from personal_ediscovery.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(root=tmp_path / "store")


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "1.txt").write_text("I love eating apples and bananas.")
    (root / "2.txt").write_text("Driving a fast sports car is exciting.")
    (root / "3.txt").write_text("The stock market experienced a sharp decline today.")
    return root


def test_vector_table_created(store: Store) -> None:
    # If sqlite-vec is installed, vec_enabled should be true
    # and the vec_documents table should exist.
    if not store.vec_enabled:
        pytest.skip("sqlite-vec not installed, skipping vector tests.")
    
    rows = store.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vec_documents'").fetchall()
    assert len(rows) == 1


def test_hybrid_search(store: Store, corpus: Path) -> None:
    if not store.vec_enabled:
        pytest.skip("sqlite-vec not installed.")
    
    embedder = EmbeddingService.load()
    if not embedder:
        pytest.skip("sentence-transformers not installed.")

    store.create_collection("mixed", str(corpus), "fs-text")
    n = index_collection(store, "mixed")
    assert n == 3

    # "fruit" does not appear in text (no BM25 match) but semantically matches apples and bananas
    hits = search(store, "fruit", "mixed")
    assert len(hits) >= 1
    assert "apples and bananas" in hits[0].snippet

    # "finance" matches the stock market semantically
    hits2 = search(store, "finance", "mixed")
    assert len(hits2) >= 1
    assert "stock market" in hits2[0].snippet
