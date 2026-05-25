"""Local embedding service using sentence-transformers.

Falls back gracefully when the ``sentence-transformers`` package is not
installed — callers should check ``EmbeddingService.available`` before
attempting to embed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Default model ships 384-dim embeddings and runs well on CPU / Apple Silicon.
DEFAULT_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


class EmbeddingService:
    """Thin wrapper around ``SentenceTransformer``.

    Construct with ``EmbeddingService.load()`` which returns ``None`` when the
    library is missing so call sites can branch on the result.
    """

    def __init__(self, model: object) -> None:
        self._model = model

    @classmethod
    def load(cls, model_name: str = DEFAULT_MODEL) -> "EmbeddingService | None":
        """Try to load the embedding model; return *None* on failure."""
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
            import logging
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
        except ImportError:
            logger.info("sentence-transformers not installed — vector search disabled.")
            return None

        try:
            model = SentenceTransformer(model_name)
            return cls(model)
        except Exception:
            logger.warning("Failed to load embedding model %s", model_name, exc_info=True)
            return None

    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> "NDArray[np.float32]":
        """Return an (N, EMBEDDING_DIM) float32 array of embeddings."""
        if not texts:
            return np.empty((0, EMBEDDING_DIM), dtype=np.float32)
        vecs = self._model.encode(texts, show_progress_bar=False, convert_to_numpy=True)  # type: ignore[union-attr]
        return vecs.astype(np.float32)

    def embed_query(self, query: str) -> "NDArray[np.float32]":
        """Embed a single query string and return a 1-D float32 vector."""
        vecs = self.embed([query])
        return vecs[0]
