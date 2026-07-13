"""Deterministic bilingual text metrics and rule-based mechanical evaluation."""

import re
from collections import Counter
from statistics import fmean, pstdev

from storyforge.enums import ConflictSeverity
from storyforge.evaluation.config import MechanicalEvaluationConfig
from storyforge.evaluation.models import (
    MechanicalEvaluationRequest,
    MechanicalEvaluationResult,
    MechanicalIssue,
    MechanicalMetrics,
)
from storyforge.evaluation.scoring import score_after_penalties

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:\.\d+)?")
_SENTENCE_SPLIT_RE = re.compile(r"[\u3002\uFF01\uFF1F!?\.]+")
_DIALOGUE_RE = re.compile(r"[\"\u201C\u2018](.*?)[\"\u201D\u2019]", re.DOTALL)
_PUNCT_RE = re.compile(r"[\uFF0C\u3002\uFF01\uFF1F\uFF1B\uFF1A,.!?;:\-\u2014\u2026]")
_REPEATED_PUNCT_RE = re.compile(r"([!?\uFF01\uFF1F\u3002\uFF0C,.])\1{2,}")
_HEADING_RE = re.compile(
    r"^\s*(第\s*\d+\s*章|chapter\s+\d+|摘要\s*[:\uFF1A]|summary\s*:)",
    re.I,
)


def _word_count(content: str) -> int:
    return len(_CJK_RE.findall(content)) + len(_WORD_RE.findall(content))


def _normalized_text(value: str) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]", "", value.casefold())


class MechanicalEvaluator:
    """Evaluate chapter mechanics without LLM calls, network, or persistence."""

    def __init__(self, config: MechanicalEvaluationConfig | None = None) -> None:
        self.config = config or MechanicalEvaluationConfig()

    def evaluate(self, request: MechanicalEvaluationRequest) -> MechanicalEvaluationResult:
        """Compute metrics and stable issues for one chapter body."""
        content = request.content.strip()
        paragraphs = [item.strip() for item in re.split(r"\n+", content) if item.strip()]
        sentences = [item.strip() for item in _SENTENCE_SPLIT_RE.split(content) if item.strip()]
        sentence_lengths = [_word_count(item) for item in sentences]
        normalized_paragraphs = [_normalized_text(item) for item in paragraphs]
        repeated_paragraph_count = sum(
            count - 1 for count in Counter(normalized_paragraphs).values() if count > 1
        )
        repeated_ngram_ratio = self._repeated_ngram_ratio(content)
        banned_phrase_count = sum(
            content.casefold().count(item.casefold()) for item in self.config.banned_phrases
        )
        dialogue_chars = sum(len(match) for match in _DIALOGUE_RE.findall(content))
        visible_chars = max(1, len(re.sub(r"\s", "", content)))
        short_ratio = (
            sum(len(item) < self.config.short_paragraph_chars for item in paragraphs)
            / len(paragraphs)
            if paragraphs
            else 0
        )
        long_ratio = (
            sum(len(item) > self.config.long_paragraph_chars for item in paragraphs)
            / len(paragraphs)
            if paragraphs
            else 0
        )
        metrics = MechanicalMetrics(
            word_count=_word_count(content),
            paragraph_count=len(paragraphs),
            sentence_count=len(sentences),
            average_sentence_length=fmean(sentence_lengths) if sentence_lengths else 0,
            sentence_length_stddev=(pstdev(sentence_lengths) if len(sentence_lengths) > 1 else 0),
            dialogue_ratio=min(1.0, dialogue_chars / visible_chars),
            repeated_paragraph_count=repeated_paragraph_count,
            repeated_ngram_ratio=repeated_ngram_ratio,
            banned_phrase_count=banned_phrase_count,
            short_paragraph_ratio=short_ratio,
            long_paragraph_ratio=long_ratio,
        )
        issues = self._detect(request, content, paragraphs, sentences, metrics)
        return MechanicalEvaluationResult(
            score=score_after_penalties(issues),
            metrics=metrics,
            issues=issues,
            evaluator_version=self.config.version,
        )

    def _issue(
        self,
        code: str,
        category: str,
        severity: ConflictSeverity,
        message: str,
        *,
        evidence: str | None = None,
        location: str | None = None,
    ) -> MechanicalIssue:
        return MechanicalIssue(
            code=code,
            category=category,
            severity=severity,
            message=message,
            evidence=evidence[:500] if evidence else None,
            location=location,
            score_penalty=self.config.penalties[code],
        )

    def _detect(
        self,
        request: MechanicalEvaluationRequest,
        content: str,
        paragraphs: list[str],
        sentences: list[str],
        metrics: MechanicalMetrics,
    ) -> list[MechanicalIssue]:
        issues: list[MechanicalIssue] = []
        if not content:
            return [
                self._issue(
                    "empty_content",
                    "length",
                    ConflictSeverity.CRITICAL,
                    "Chapter content is empty.",
                )
            ]
        if metrics.word_count < request.target_words * self.config.min_length_ratio:
            issues.append(
                self._issue(
                    "length_too_short",
                    "length",
                    ConflictSeverity.HIGH,
                    "Chapter is substantially shorter than its target.",
                )
            )
        if metrics.word_count > request.target_words * self.config.max_length_ratio:
            issues.append(
                self._issue(
                    "length_too_long",
                    "length",
                    ConflictSeverity.MEDIUM,
                    "Chapter is substantially longer than its target.",
                )
            )
        if metrics.repeated_paragraph_count:
            issues.append(
                self._issue(
                    "duplicate_paragraph",
                    "repetition",
                    ConflictSeverity.HIGH,
                    "One or more paragraphs are exact duplicates.",
                )
            )
        if metrics.repeated_ngram_ratio > self.config.repeated_ngram_ratio_threshold:
            issues.append(
                self._issue(
                    "repeated_ngram_high",
                    "repetition",
                    ConflictSeverity.MEDIUM,
                    "Repeated n-grams occupy too much of the chapter.",
                )
            )
        if (
            len(sentences) >= self.config.sentence_uniformity_min_count
            and metrics.sentence_length_stddev < self.config.sentence_stddev_min
        ):
            issues.append(
                self._issue(
                    "uniform_sentence_lengths",
                    "style",
                    ConflictSeverity.LOW,
                    "Sentence lengths are unusually uniform.",
                )
            )
        if self._similar_opening_run(paragraphs) >= self.config.similar_opening_run:
            issues.append(
                self._issue(
                    "similar_paragraph_openings",
                    "style",
                    ConflictSeverity.LOW,
                    "Several consecutive paragraphs use the same opening pattern.",
                )
            )
        ai_matches = [
            phrase for phrase in self.config.ai_phrases if phrase.casefold() in content.casefold()
        ]
        if ai_matches:
            issues.append(
                self._issue(
                    "ai_cliche",
                    "style",
                    ConflictSeverity.MEDIUM,
                    "High-frequency generic AI phrasing was detected.",
                    evidence=", ".join(ai_matches),
                )
            )
        banned_matches = [
            phrase
            for phrase in self.config.banned_phrases
            if phrase.casefold() in content.casefold()
        ]
        if banned_matches:
            issues.append(
                self._issue(
                    "banned_phrase",
                    "safety",
                    ConflictSeverity.HIGH,
                    "Configured banned phrasing was detected.",
                    evidence=", ".join(banned_matches),
                )
            )
        excessive_marks = len(re.findall(r"\u2014|\u2026|!|\uFF01", content))
        if excessive_marks / visible_units(content) * 100 > self.config.punctuation_per_100_limit:
            issues.append(
                self._issue(
                    "punctuation_overuse",
                    "punctuation",
                    ConflictSeverity.MEDIUM,
                    "Dashes, ellipses, or exclamation marks are overused.",
                )
            )
        if len(content) >= self.config.dialogue_check_min_chars:
            if metrics.dialogue_ratio > self.config.dialogue_ratio_max:
                issues.append(
                    self._issue(
                        "dialogue_ratio_high",
                        "dialogue",
                        ConflictSeverity.MEDIUM,
                        "Dialogue occupies an unusually high share of the chapter.",
                    )
                )
            elif metrics.dialogue_ratio < self.config.dialogue_ratio_min:
                issues.append(
                    self._issue(
                        "dialogue_ratio_low",
                        "dialogue",
                        ConflictSeverity.LOW,
                        "Dialogue is nearly absent from a dialogue-sized chapter.",
                    )
                )
        if metrics.long_paragraph_ratio > self.config.long_paragraph_ratio_limit:
            issues.append(
                self._issue(
                    "long_paragraph",
                    "paragraph",
                    ConflictSeverity.MEDIUM,
                    "Too many paragraphs exceed the configured length.",
                )
            )
        if (
            len(paragraphs) >= 3
            and metrics.short_paragraph_ratio > self.config.short_paragraph_ratio_limit
        ):
            issues.append(
                self._issue(
                    "short_paragraphs",
                    "paragraph",
                    ConflictSeverity.MEDIUM,
                    "A large share of paragraphs are extremely short.",
                )
            )
        punctuation_ratio = len(_PUNCT_RE.findall(content)) / visible_units(content)
        if punctuation_ratio > self.config.punctuation_ratio_limit or _REPEATED_PUNCT_RE.search(
            content
        ):
            issues.append(
                self._issue(
                    "punctuation_anomaly",
                    "punctuation",
                    ConflictSeverity.MEDIUM,
                    "Punctuation density or repetition is abnormal.",
                )
            )
        if _HEADING_RE.search(content):
            issues.append(
                self._issue(
                    "embedded_heading_or_summary",
                    "structure",
                    ConflictSeverity.MEDIUM,
                    "A chapter heading or summary appears to be mixed into the body.",
                )
            )
        return issues

    def _repeated_ngram_ratio(self, content: str) -> float:
        normalized = _normalized_text(content)
        size = self.config.ngram_size
        if len(normalized) < size:
            return 0
        ngrams = [normalized[index : index + size] for index in range(len(normalized) - size + 1)]
        counts = Counter(ngrams)
        repeated = sum(count - 1 for count in counts.values() if count > 1)
        return min(1.0, repeated / len(ngrams))

    def _similar_opening_run(self, paragraphs: list[str]) -> int:
        openings = [
            _normalized_text(item)[: self.config.similar_opening_length] for item in paragraphs
        ]
        longest = current = 0
        previous = None
        for opening in openings:
            if opening and opening == previous:
                current += 1
            else:
                current = 1 if opening else 0
            longest = max(longest, current)
            previous = opening
        return longest


def visible_units(content: str) -> int:
    """Return a non-zero visible-character denominator for tiny inputs."""
    return max(1, len(re.sub(r"\s", "", content)))
