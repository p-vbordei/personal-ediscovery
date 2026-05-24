from pathlib import Path

import pytest

from personal_ediscovery.services import index_collection, search
from personal_ediscovery.store import Store


@pytest.fixture
def tmp_corpus(tmp_path: Path) -> Path:
    (tmp_path / "a.md").write_text("Kitchen renovation budget: $20000. Tile, cabinets, plumbing.")
    (tmp_path / "b.md").write_text("Vacation plan to Lisbon for next summer.")
    (tmp_path / "c.txt").write_text("Old roommate left their things in storage unit B.")
    return tmp_path


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(root=tmp_path / "store")


def test_index_and_search(store: Store, tmp_corpus: Path) -> None:
    store.create_collection("notes", str(tmp_corpus), "fs-text")
    n = index_collection(store, "notes")
    assert n == 3
    hits = search(store, "kitchen", "notes")
    assert len(hits) >= 1
    assert any("Kitchen" in h.snippet or "kitchen" in h.snippet.lower() for h in hits)


def test_forget(store: Store, tmp_corpus: Path) -> None:
    store.create_collection("notes", str(tmp_corpus), "fs-text")
    index_collection(store, "notes")
    n = store.forget("notes", "roommate")
    assert n == 1
    hits = search(store, "roommate", "notes")
    assert hits == []
