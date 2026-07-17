"""Structure-first deterministic text chunking for Chinese and English prose."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from storyforge.memory.models import ChunkDraft

_SENTENCE_BOUNDARY = re.compile(
    r"(?<=[\u3002\uff01\uff1f.!?])(?:[\"'\u201d\u2019\uff09\u3011]?)\s*"
)
_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    target_chars: int = 1200
    max_chars: int = 1800
    overlap_chars: int = 150
    max_chunks_per_source: int = 200
    token_estimator_version: str = "char-cjk-v1"

    def __post_init__(self) -> None:
        if self.target_chars < 50 or self.max_chars < self.target_chars:
            raise ValueError("Chunk target and maximum sizes are invalid")
        if self.overlap_chars < 0 or self.overlap_chars >= self.target_chars:
            raise ValueError("Chunk overlap must be smaller than target size")
        if self.max_chunks_per_source < 1:
            raise ValueError("Chunk count limit must be positive")


class MemoryChunker:
    """Split headings, paragraphs and sentences before using a hard character limit."""

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()

    def chunk(
        self,
        content: str,
        *,
        source_type: str,
        language: str = "zh-CN",
        metadata: dict[str, object] | None = None,
    ) -> list[ChunkDraft]:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            return []
        structural = self._structural_segments(normalized)
        pieces: list[str] = []
        for segment in structural:
            pieces.extend(self._bounded_segments(segment))
        chunks: list[str] = []
        current = ""
        for piece in pieces:
            separator = "\n\n" if current else ""
            if current and len(current) + len(separator) + len(piece) > self.config.target_chars:
                chunks.append(current.strip())
                overlap = self._overlap(current)
                current = f"{overlap}\n\n{piece}".strip() if overlap else piece
            else:
                current = f"{current}{separator}{piece}".strip()
            if len(current) > self.config.max_chars:
                chunks.extend(self._hard_split(current)[:-1])
                current = self._hard_split(current)[-1]
        if current:
            chunks.append(current.strip())
        chunks = [item for item in chunks if item]
        if len(chunks) > self.config.max_chunks_per_source:
            raise ValueError("Source exceeds the configured memory chunk limit")
        base_metadata = {
            "source_type": source_type,
            "language": language,
            "token_estimator": self.config.token_estimator_version,
            **(metadata or {}),
        }
        return [
            ChunkDraft(
                chunk_index=index,
                content=item,
                content_hash=hashlib.sha256(item.encode("utf-8")).hexdigest(),
                token_estimate=self._token_estimate(item),
                character_count=len(item),
                metadata=base_metadata,
            )
            for index, item in enumerate(chunks)
        ]

    @staticmethod
    def _structural_segments(content: str) -> list[str]:
        content = _HEADING.sub(lambda match: f"\n\n{match.group(0)}", content)
        return [part.strip() for part in re.split(r"\n\s*\n+", content) if part.strip()]

    def _bounded_segments(self, segment: str) -> list[str]:
        if len(segment) <= self.config.max_chars:
            return [segment]
        sentences = [item.strip() for item in _SENTENCE_BOUNDARY.split(segment) if item.strip()]
        if len(sentences) <= 1:
            return self._hard_split(segment)
        output: list[str] = []
        current = ""
        for sentence in sentences:
            if len(sentence) > self.config.max_chars:
                if current:
                    output.append(current)
                    current = ""
                output.extend(self._hard_split(sentence))
            elif current and len(current) + len(sentence) > self.config.max_chars:
                output.append(current)
                current = sentence
            else:
                current += sentence
        if current:
            output.append(current)
        return output

    def _hard_split(self, value: str) -> list[str]:
        return [
            value[start : start + self.config.max_chars].strip()
            for start in range(0, len(value), self.config.max_chars)
            if value[start : start + self.config.max_chars].strip()
        ]

    def _overlap(self, value: str) -> str:
        if not self.config.overlap_chars:
            return ""
        tail = value[-self.config.overlap_chars :]
        boundary = max(
            tail.find("\u3002"),
            tail.find("\uff01"),
            tail.find("\uff1f"),
            tail.find(". "),
        )
        return tail[boundary + 1 :].strip() if boundary >= 0 else tail.strip()

    @staticmethod
    def _token_estimate(value: str) -> int:
        cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", value))
        non_cjk = len(value) - cjk
        return cjk + math.ceil(non_cjk / 4)
