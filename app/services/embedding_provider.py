import hashlib
import json
import math
from typing import List, Optional

from app.core.config import settings


LOCAL_EMBEDDING_DIMENSIONS = 64


def normalize_embedding_text(text: str) -> str:
    return text.lower().replace(" ", "")


class LocalEmbeddingProvider:
    name = "local_hash"

    def __init__(self, dimensions: int = LOCAL_EMBEDDING_DIMENSIONS):
        self.dimensions = dimensions

    def embed_text(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        normalized_text = normalize_embedding_text(text)
        if not normalized_text:
            return vector

        for char in normalized_text:
            digest = hashlib.md5(char.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % self.dimensions
            vector[index] += 1.0

        length = math.sqrt(sum(value * value for value in vector))
        if length == 0:
            return vector
        return [round(value / length, 6) for value in vector]


def get_embedding_provider(provider_name: Optional[str] = None) -> LocalEmbeddingProvider:
    selected_provider = (provider_name or settings.embedding_provider).strip().lower()
    if selected_provider != LocalEmbeddingProvider.name:
        return LocalEmbeddingProvider()
    return LocalEmbeddingProvider()


def create_local_embedding(text: str, dimensions: int = LOCAL_EMBEDDING_DIMENSIONS) -> List[float]:
    return LocalEmbeddingProvider(dimensions=dimensions).embed_text(text)


def serialize_embedding(embedding: List[float]) -> str:
    return json.dumps(embedding, ensure_ascii=False)


def parse_embedding(value: Optional[str]) -> List[float]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [float(item) for item in parsed if isinstance(item, (int, float))]


def cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot_product = sum(a * b for a, b in zip(left, right))
    left_length = math.sqrt(sum(a * a for a in left))
    right_length = math.sqrt(sum(b * b for b in right))
    if left_length == 0 or right_length == 0:
        return 0.0
    return dot_product / (left_length * right_length)
