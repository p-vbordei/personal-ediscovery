"""Source adapters that discover content for indexing."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterator, Protocol

from .models import SourceItem


class SourceAdapter(Protocol):
    name: str
    def discover(self, root: Path) -> Iterator[SourceItem]: ...


class FsTextAdapter:
    name = "fs-text"

    EXTENSIONS = {".txt", ".md", ".markdown", ".text"}

    def discover(self, root: Path) -> Iterator[SourceItem]:
        if not root.exists():
            return
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.EXTENSIONS:
                continue
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            stat = path.stat()
            yield SourceItem(
                source_ref=str(path),
                title=path.name,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
                body=body,
                meta={"size_bytes": stat.st_size},
            )


REGISTRY: dict[str, SourceAdapter] = {
    "fs-text": FsTextAdapter(),
}


def get_adapter(name: str) -> SourceAdapter:
    if name not in REGISTRY:
        raise KeyError(f"Unknown adapter: {name}. Available: {', '.join(REGISTRY)}")
    return REGISTRY[name]
