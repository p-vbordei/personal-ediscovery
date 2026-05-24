"""End-to-end scenario over a small fake personal corpus."""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_ediscovery.services import index_collection, search
from personal_ediscovery.store import Store


CORPUS: dict[str, str] = {
    "kitchen.md": "Kitchen renovation budget: $20000 — tile, cabinets, plumbing.",
    "vacation.md": "Vacation plan to Lisbon for next summer.",
    "roommate.txt": "Old roommate Sarah left her things in storage unit B.",
    "acme_invoice_jan.md": "Acme Corp invoice January 2026: $4,500.",
    "acme_invoice_feb.md": "Acme Corp invoice February 2026: $5,200.",
    "acme_followup.md": "Follow up with Acme Corp about late payment.",
    "globex_invoice.md": "Globex Inc invoice March 2026: $1,000.",
    "doctor.md": "Annual physical at Dr. Patel's office next Tuesday.",
    "groceries.md": "Buy milk, eggs, bread, coffee, and avocados.",
    "books.md": "Reading list: 'Designing Data-Intensive Applications'.",
    "movies.md": "Watchlist: Dune Part Two, Oppenheimer, Past Lives.",
    "github.md": "Personal projects: research_capabilities, personal-ediscovery.",
    "passwords_hint.md": "Reminder: rotate the wifi password each quarter.",
    "car.md": "Toyota service: oil change at 60k miles.",
    "rent.md": "Rent due first of the month, $2,300.",
    "birthdays.md": "Mom — March 12. Dad — July 4. Sister — Nov 23.",
    "recipes.md": "Pasta carbonara: eggs, pecorino, guanciale, pepper.",
    "todo.md": "Renew passport before June. Schedule dentist.",
    "ideas.md": "App idea: local-first personal search with consent tokens.",
    "notes_misc.md": "Random thought: kitchen tile prices vary a lot.",
}


@pytest.fixture
def corpus_root(tmp_path: Path) -> Path:
    root = tmp_path / "personal"
    root.mkdir()
    for name, body in CORPUS.items():
        (root / name).write_text(body)
    return root


@pytest.fixture
def indexed(tmp_path: Path, corpus_root: Path) -> Store:
    store = Store(root=tmp_path / "store")
    store.create_collection("personal", str(corpus_root), "fs-text")
    n = index_collection(store, "personal")
    assert n == len(CORPUS)
    return store


def test_corpus_indexes_all_files(indexed: Store) -> None:
    assert indexed.count_documents("personal") == len(CORPUS)


def test_corpus_search_various_queries(indexed: Store) -> None:
    queries_with_expected_substring = {
        "kitchen": "kitchen",
        "Acme": "acme",
        "Lisbon": "lisbon",
        "roommate": "roommate",
        "passport": "passport",
    }
    for q, expected in queries_with_expected_substring.items():
        hits = search(indexed, q, "personal")
        assert len(hits) >= 1, f"expected hits for {q!r}"
        assert any(
            expected in (h.snippet or "").lower() for h in hits
        ), f"snippet for {q!r} missing expected token"


def test_forget_acme_corp_then_search_empty(indexed: Store) -> None:
    # Three documents contain "Acme Corp" in the corpus.
    before = search(indexed, "Acme Corp", "personal")
    assert len(before) >= 3

    removed = indexed.forget("personal", "Acme Corp")
    assert removed == 3

    after = search(indexed, "Acme Corp", "personal")
    assert after == []


def test_tombstone_count_matches_removed(indexed: Store) -> None:
    removed = indexed.forget("personal", "Acme Corp")
    tomb_count = indexed.db.execute(
        "SELECT count(*) FROM tombstones WHERE collection = ? AND query = ?",
        ("personal", "Acme Corp"),
    ).fetchone()[0]
    assert tomb_count == removed
    assert tomb_count == 3


def test_remaining_corpus_unaffected_by_forget(indexed: Store) -> None:
    indexed.forget("personal", "Acme Corp")
    # An unrelated query should still find its document.
    hits = search(indexed, "Lisbon", "personal")
    assert len(hits) == 1
    assert indexed.count_documents("personal") == len(CORPUS) - 3
