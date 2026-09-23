"""Embedding providers.

* ``HashingEmbeddingProvider`` — deterministic, dependency-free *lexical* embeddings (feature hashing of
  word unigrams, bigrams and character trigrams plus a small synonym table). It is NOT a neural model:
  it captures vocabulary overlap and fuzzy spelling, not deep semantics. It exists so vector search works
  in every environment (CI, offline dev) and is labelled as such everywhere it is reported.
* ``FastEmbedProvider`` — local neural embeddings (BAAI/bge-small-en-v1.5, 384-d) when ``fastembed`` is
  installed.
* ``OpenAICompatibleEmbeddingProvider`` — any OpenAI-compatible ``/embeddings`` endpoint.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

import httpx

from genora.errors import ProviderUnavailableError

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")

# Small, domain-oriented synonym table: maps a surface form to a canonical concept token.
SYNONYMS: dict[str, str] = {
    "ultrabook": "laptop", "macbook": "laptop", "chromebook": "laptop",
    "sneaker": "shoe", "sneakers": "shoe", "trainer": "shoe", "trainers": "shoe", "shoes": "shoe",
    "footwear": "shoe", "runners": "shoe",
    "earbud": "headphone", "earbuds": "headphone", "headset": "headphone", "headphones": "headphone",
    "earphone": "headphone", "earphones": "headphone", "iem": "headphone",
    "tv": "television", "telly": "television",
    "smartphone": "phone", "cellphone": "phone", "mobile": "phone", "handset": "phone",
    "tablet": "tablet", "ipad": "tablet",
    "camera": "camera", "dslr": "camera", "mirrorless": "camera",
    "lens": "lens", "lenses": "lens", "tripod": "tripod",
    "couch": "sofa", "settee": "sofa",
    "jogging": "running", "run": "running", "marathon": "running",
    "coding": "programming", "developer": "programming", "code": "programming", "software": "programming",
    "gaming": "game", "gamer": "game", "games": "game",
    "cheap": "budget", "affordable": "budget", "inexpensive": "budget",
    "kids": "child", "children": "child", "toddler": "child",
    "watch": "watch", "smartwatch": "watch", "wearable": "watch",
    "backpack": "bag", "rucksack": "bag", "daypack": "bag",
    "moisturiser": "moisturizer", "skincare": "skin",
    "blender": "blender", "mixer": "blender",
    "speaker": "speaker", "soundbar": "speaker",
    "jacket": "jacket", "coat": "jacket", "parka": "jacket",
    "yoga": "yoga", "pilates": "yoga",
}

STOPWORDS = frozenset(
    "a an the and or for with to of in on at by from is are be i me my we you your it this that these those "
    "need want looking find show get buy some any good best under over below above around about".split()
)


def _stem(token: str) -> str:
    for suffix in ("ing", "es", "s"):
        if len(token) > 4 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


class EmbeddingProvider(ABC):
    name: str
    model: str
    dimensions: int
    is_neural: bool

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def describe(self) -> dict[str, object]:
        return {"provider": self.name, "model": self.model, "dimensions": self.dimensions, "neural": self.is_neural}


class HashingEmbeddingProvider(EmbeddingProvider):
    name = "hashing"
    is_neural = False

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions
        self.model = f"feature-hashing-v1-{dimensions}"

    def _index(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        value = int.from_bytes(digest, "little")
        return value % self.dimensions, (1.0 if (value >> 63) & 1 else -1.0)

    def _features(self, text: str) -> list[tuple[str, float]]:
        feats: list[tuple[str, float]] = []
        tokens = tokenize(text)
        concepts = []
        for tok in tokens:
            stem = _stem(tok)
            concept = SYNONYMS.get(tok) or SYNONYMS.get(stem) or stem
            concepts.append(concept)
            feats.append(("w:" + concept, 1.0))
            if concept != tok:
                feats.append(("w:" + tok, 0.5))
            padded = f"#{stem}#"
            for i in range(len(padded) - 2):
                feats.append(("c:" + padded[i : i + 3], 0.25))
        for a, b in zip(concepts, concepts[1:], strict=False):
            feats.append((f"b:{a}_{b}", 0.6))
        return feats

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dimensions
            for feature, weight in self._features(text):
                idx, sign = self._index(feature)
                vec[idx] += sign * weight
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class FastEmbedProvider(EmbeddingProvider):
    """Local neural embeddings via the optional `fastembed` package (ONNX, CPU)."""

    name = "fastembed"
    is_neural = True

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5", dimensions: int = 384) -> None:
        try:
            from fastembed import TextEmbedding  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise ProviderUnavailableError("fastembed is not installed (pip install 'genora[fastembed]')") from exc
        self.model = model
        self.dimensions = dimensions
        self._model = TextEmbedding(model_name=model)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:  # pragma: no cover - optional
        vectors = [list(map(float, v)) for v in self._model.embed(list(texts))]
        if vectors and len(vectors[0]) != self.dimensions:
            raise ProviderUnavailableError(f"{self.model} returned {len(vectors[0])}-d vectors, expected {self.dimensions}")
        return vectors


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    name = "openai_compatible"
    is_neural = True

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        dimensions: int = 384,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            resp = self._client.post(
                "/embeddings", json={"model": self.model, "input": list(texts), "dimensions": self.dimensions}
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"embedding request failed: {type(exc).__name__}") from exc
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
