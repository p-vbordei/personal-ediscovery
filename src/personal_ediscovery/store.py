"""SQLite-backed store for collections, documents, tombstones."""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable
from uuid import UUID

from .models import Collection, Document

DEFAULT_DIR = Path.home() / ".personal-ediscovery"
DB_NAME = "store.sqlite"


def _sanitize_fts_query(query: str) -> str:
    """Turn a free-form user query into a safe FTS5 MATCH expression.

    FTS5 treats characters like ``+``, ``(``, ``"`` and bareword operators
    (``AND``/``OR``/``NOT``/``NEAR``) as syntax. Rather than expose that to
    the CLI user, we extract alphanumeric/underscore tokens and quote each
    one, joining with implicit AND. Empty input becomes a query that matches
    nothing.
    """
    import re

    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    if not tokens:
        # FTS5 requires a non-empty MATCH; use a token unlikely to appear.
        return '"__personal_ediscovery_no_match__"'
    return " ".join(f'"{t}"' for t in tokens)


class Store:
    def __init__(self, root: Path | None = None) -> None:
        # Resolve lazily so monkeypatching `store.DEFAULT_DIR` in tests works.
        self.root = root if root is not None else DEFAULT_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / DB_NAME)
        self.db.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.db.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS collections(
              name TEXT PRIMARY KEY,
              root TEXT NOT NULL,
              adapter TEXT NOT NULL,
              created_at TEXT NOT NULL,
              consent_token TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents(
              id TEXT PRIMARY KEY,
              collection TEXT NOT NULL,
              source_ref TEXT NOT NULL,
              title TEXT,
              modified_at TEXT,
              body TEXT NOT NULL,
              meta_json TEXT,
              FOREIGN KEY(collection) REFERENCES collections(name)
            );
            CREATE INDEX IF NOT EXISTS documents_collection ON documents(collection);
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
              body, title, content='documents', content_rowid='rowid'
            );
            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
              INSERT INTO documents_fts(rowid, body, title) VALUES (new.rowid, new.body, new.title);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
              INSERT INTO documents_fts(documents_fts, rowid, body, title) VALUES('delete', old.rowid, old.body, old.title);
            END;
            CREATE TABLE IF NOT EXISTS tombstones(
              id TEXT NOT NULL,
              collection TEXT NOT NULL,
              removed_at TEXT NOT NULL,
              query TEXT
            );
        """)
        self.db.commit()

    def create_collection(self, name: str, root: str, adapter: str) -> Collection:
        col = Collection(name=name, root=root, adapter=adapter, consent_token=secrets.token_urlsafe(16))
        self.db.execute(
            "INSERT INTO collections(name, root, adapter, created_at, consent_token) VALUES (?, ?, ?, ?, ?)",
            (col.name, col.root, col.adapter, col.created_at.isoformat(), col.consent_token),
        )
        self.db.commit()
        return col

    def list_collections(self) -> list[Collection]:
        rows = self.db.execute("SELECT name, root, adapter, created_at, consent_token FROM collections").fetchall()
        return [
            Collection(
                name=r[0],
                root=r[1],
                adapter=r[2],
                created_at=datetime.fromisoformat(r[3]),
                consent_token=r[4],
            )
            for r in rows
        ]

    def get_collection(self, name: str) -> Collection | None:
        row = self.db.execute(
            "SELECT name, root, adapter, created_at, consent_token FROM collections WHERE name = ?",
            (name,),
        ).fetchone()
        if not row:
            return None
        return Collection(
            name=row[0], root=row[1], adapter=row[2],
            created_at=datetime.fromisoformat(row[3]), consent_token=row[4],
        )

    def add_documents(self, collection: str, items: Iterable[Document]) -> int:
        n = 0
        for d in items:
            self.db.execute(
                "INSERT INTO documents(id, collection, source_ref, title, modified_at, body, meta_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(d.id),
                    collection,
                    d.source_ref,
                    d.title,
                    d.modified_at.isoformat() if d.modified_at else None,
                    d.body,
                    json.dumps(d.meta),
                ),
            )
            n += 1
        self.db.commit()
        return n

    def clear_collection(self, collection: str) -> int:
        """Delete all documents in a collection (without recording tombstones).

        Used by re-index to avoid appending duplicate rows for the same source.
        """
        rows = self.db.execute(
            "SELECT id FROM documents WHERE collection = ?", (collection,)
        ).fetchall()
        ids = [r[0] for r in rows]
        for did in ids:
            self.db.execute("DELETE FROM documents WHERE id = ?", (did,))
        self.db.commit()
        return len(ids)

    def count_documents(self, collection: str) -> int:
        row = self.db.execute("SELECT count(*) FROM documents WHERE collection = ?", (collection,)).fetchone()
        return int(row[0]) if row else 0

    def search_bm25(self, query: str, collection: str | None, k: int = 10) -> list[tuple[Document, float]]:
        sql = (
            "SELECT d.id, d.collection, d.source_ref, d.title, d.modified_at, d.body, d.meta_json, bm25(documents_fts) "
            "FROM documents_fts JOIN documents d ON d.rowid = documents_fts.rowid "
            "WHERE documents_fts MATCH ?"
        )
        args: list[str | int] = [_sanitize_fts_query(query)]
        if collection:
            sql += " AND d.collection = ?"
            args.append(collection)
        sql += " ORDER BY bm25(documents_fts) LIMIT ?"
        args.append(k)
        rows = self.db.execute(sql, args).fetchall()
        out: list[tuple[Document, float]] = []
        for r in rows:
            d = Document(
                id=UUID(r[0]),
                collection=r[1],
                source_ref=r[2],
                title=r[3],
                modified_at=datetime.fromisoformat(r[4]) if r[4] else None,
                body=r[5],
                meta=json.loads(r[6]) if r[6] else {},
            )
            out.append((d, float(r[7])))
        return out

    def forget(self, collection: str, query: str) -> int:
        rows = self.db.execute(
            "SELECT id FROM documents WHERE collection = ? AND body LIKE ?",
            (collection, f"%{query}%"),
        ).fetchall()
        ids = [r[0] for r in rows]
        for did in ids:
            self.db.execute("DELETE FROM documents WHERE id = ?", (did,))
            self.db.execute(
                "INSERT INTO tombstones(id, collection, removed_at, query) VALUES (?, ?, ?, ?)",
                (did, collection, datetime.now().isoformat(), query),
            )
        self.db.commit()
        return len(ids)
