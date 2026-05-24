"""Edge-case coverage for Store, FsTextAdapter, make_snippet, and the pipeline."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from personal_ediscovery.adapters import FsTextAdapter
from personal_ediscovery.services import index_collection, make_snippet, search
from personal_ediscovery.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(root=tmp_path / "store")


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def test_empty_store_lists_no_collections(store: Store) -> None:
    assert store.list_collections() == []


def test_empty_store_counts_zero(store: Store) -> None:
    assert store.count_documents("nope") == 0


def test_empty_store_search_returns_empty(store: Store) -> None:
    assert store.search_bm25("anything", None) == []


def test_duplicate_collection_raises(store: Store) -> None:
    store.create_collection("notes", "/tmp", "fs-text")
    with pytest.raises(sqlite3.IntegrityError):
        store.create_collection("notes", "/tmp", "fs-text")


def test_search_filters_by_collection(store: Store, tmp_path: Path) -> None:
    a_root = tmp_path / "a"
    b_root = tmp_path / "b"
    a_root.mkdir()
    b_root.mkdir()
    (a_root / "x.md").write_text("alpha kitchen")
    (b_root / "y.md").write_text("beta kitchen")

    store.create_collection("acol", str(a_root), "fs-text")
    store.create_collection("bcol", str(b_root), "fs-text")
    index_collection(store, "acol")
    index_collection(store, "bcol")

    hits_a = search(store, "kitchen", "acol")
    hits_b = search(store, "kitchen", "bcol")
    hits_all = search(store, "kitchen", None)

    assert {h.collection for h in hits_a} == {"acol"}
    assert {h.collection for h in hits_b} == {"bcol"}
    assert {h.collection for h in hits_all} == {"acol", "bcol"}


def test_consent_token_unique_per_collection(store: Store) -> None:
    a = store.create_collection("a", "/tmp", "fs-text")
    b = store.create_collection("b", "/tmp", "fs-text")
    assert a.consent_token != b.consent_token
    assert a.consent_token  # non-empty
    assert b.consent_token


def test_forget_no_match(store: Store, tmp_path: Path) -> None:
    root = tmp_path / "c"
    root.mkdir()
    (root / "x.md").write_text("nothing relevant here")
    store.create_collection("c", str(root), "fs-text")
    index_collection(store, "c")

    removed = store.forget("c", "needle-that-is-absent")
    assert removed == 0

    tomb = store.db.execute(
        "SELECT count(*) FROM tombstones WHERE collection = ?", ("c",)
    ).fetchone()[0]
    assert tomb == 0


def test_forget_records_tombstones(store: Store, tmp_path: Path) -> None:
    root = tmp_path / "d"
    root.mkdir()
    (root / "x.md").write_text("Acme Corp invoice")
    (root / "y.md").write_text("Acme Corp follow-up")
    (root / "z.md").write_text("unrelated note")
    store.create_collection("d", str(root), "fs-text")
    index_collection(store, "d")

    removed = store.forget("d", "Acme Corp")
    assert removed == 2

    rows = store.db.execute(
        "SELECT collection, query FROM tombstones WHERE collection = ?", ("d",)
    ).fetchall()
    assert len(rows) == 2
    assert all(r[0] == "d" and r[1] == "Acme Corp" for r in rows)


# ---------------------------------------------------------------------------
# FsTextAdapter
# ---------------------------------------------------------------------------


def test_adapter_skips_non_text_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("text")
    (tmp_path / "b.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "c.pdf").write_bytes(b"%PDF-1.4 fake")

    items = list(FsTextAdapter().discover(tmp_path))
    names = {Path(i.source_ref).name for i in items}
    assert names == {"a.md"}


def test_adapter_recurses_into_subdirs(tmp_path: Path) -> None:
    sub = tmp_path / "deep" / "nested"
    sub.mkdir(parents=True)
    (sub / "buried.md").write_text("found me")
    items = list(FsTextAdapter().discover(tmp_path))
    assert any(Path(i.source_ref).name == "buried.md" for i in items)


def test_adapter_skips_broken_symlinks(tmp_path: Path) -> None:
    # Broken symlink: target doesn't exist. rglob will yield it but is_file()
    # returns False, so the adapter must silently skip without error.
    target = tmp_path / "missing.md"
    link = tmp_path / "broken.md"
    os.symlink(target, link)
    (tmp_path / "real.md").write_text("ok")

    items = list(FsTextAdapter().discover(tmp_path))
    names = {Path(i.source_ref).name for i in items}
    assert names == {"real.md"}


def test_adapter_indexes_empty_file(tmp_path: Path) -> None:
    (tmp_path / "empty.md").write_text("")
    items = list(FsTextAdapter().discover(tmp_path))
    assert len(items) == 1
    assert items[0].body == ""


def test_adapter_preserves_unicode(tmp_path: Path) -> None:
    content = "Café résumé 日本語 🎉"
    (tmp_path / "u.md").write_text(content)
    items = list(FsTextAdapter().discover(tmp_path))
    assert items[0].body == content


def test_adapter_nonexistent_root_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    items = list(FsTextAdapter().discover(missing))
    assert items == []


# ---------------------------------------------------------------------------
# make_snippet
# ---------------------------------------------------------------------------


def test_snippet_query_not_found_returns_prefix() -> None:
    body = "a" * 500
    snip = make_snippet(body, "zzz", radius=10)
    # first 2*radius chars, plus ellipsis since body is longer
    assert snip.startswith("a" * 20)
    assert snip.endswith("…")


def test_snippet_query_at_start() -> None:
    body = "kitchen renovation budget for the house"
    snip = make_snippet(body, "kitchen", radius=10)
    assert snip.startswith("kitchen")
    # Should be windowed (ellipsis at end since body extends past idx+len+radius)
    assert snip.endswith("…")


def test_snippet_query_in_middle_has_both_ellipses() -> None:
    body = "a" * 100 + "KITCHEN" + "b" * 100
    snip = make_snippet(body, "kitchen", radius=15)
    assert snip.startswith("…")
    assert snip.endswith("…")
    assert "KITCHEN" in snip


def test_snippet_collapses_newlines() -> None:
    body = "line1\nline2 kitchen renovation\nline3"
    snip = make_snippet(body, "kitchen", radius=10)
    assert "\n" not in snip
    assert "kitchen" in snip


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def test_reindex_does_not_duplicate(store: Store, tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.md").write_text("Kitchen renovation budget")
    (root / "b.md").write_text("Vacation in Lisbon")
    store.create_collection("r", str(root), "fs-text")

    index_collection(store, "r")
    first = store.count_documents("r")
    index_collection(store, "r")
    second = store.count_documents("r")

    assert first == 2
    assert second == 2, "re-index must truncate, not append duplicates"


def test_search_across_all_collections(store: Store, tmp_path: Path) -> None:
    for name in ("c1", "c2"):
        sub = tmp_path / name
        sub.mkdir()
        (sub / "f.md").write_text(f"{name} shared-keyword payload")
        store.create_collection(name, str(sub), "fs-text")
        index_collection(store, name)

    hits = search(store, "shared-keyword", collection=None)
    assert {h.collection for h in hits} == {"c1", "c2"}


def test_large_collection_indexes_and_searches(store: Store, tmp_path: Path) -> None:
    root = tmp_path / "big"
    root.mkdir()
    for i in range(100):
        (root / f"doc_{i:03d}.md").write_text(f"document number {i} with token tag{i}")
    store.create_collection("big", str(root), "fs-text")
    n = index_collection(store, "big")
    assert n == 100
    assert store.count_documents("big") == 100

    hits = search(store, "tag42", "big")
    assert len(hits) == 1
    assert "tag42" in hits[0].snippet


def test_search_with_fts5_special_chars_does_not_crash(store: Store, tmp_path: Path) -> None:
    root = tmp_path / "x"
    root.mkdir()
    (root / "code.md").write_text("I write c++ and python code")
    (root / "math.md").write_text("formula (a+b)*c is common")
    store.create_collection("x", str(root), "fs-text")
    index_collection(store, "x")

    # Each of these would otherwise raise sqlite3.OperationalError due to FTS5
    # syntax. Sanitized queries must succeed without error.
    for q in ["c++", "(parens)", "a AND b", '"unbalanced', "NEAR()", "!@#$%"]:
        hits = search(store, q, "x")
        assert isinstance(hits, list)

    # Confirm tokens still extracted: 'c++' should find the c++ doc.
    cpp_hits = search(store, "c++", "x")
    assert any("c++" in h.snippet for h in cpp_hits)
