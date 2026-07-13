"""Milestone-four mechanical evaluation and normalization tests."""

# ruff: noqa: RUF001 -- Chinese fixtures intentionally exercise Chinese punctuation.

import pytest

from storyforge.consistency import FactNormalizer
from storyforge.consistency.models import FactEvidence
from storyforge.evaluation import MechanicalEvaluator
from storyforge.evaluation.config import MechanicalEvaluationConfig
from storyforge.evaluation.models import MechanicalEvaluationRequest


def _evaluate(
    content: str,
    *,
    target: int = 100,
    config: MechanicalEvaluationConfig | None = None,
):
    return MechanicalEvaluator(config).evaluate(
        MechanicalEvaluationRequest(
            chapter_id=1,
            chapter_number=1,
            content=content,
            target_words=target,
        )
    )


def _codes(content: str, *, target: int = 100) -> set[str]:
    return {item.code for item in _evaluate(content, target=target).issues}


def test_empty_short_long_and_tiny_inputs_are_bounded() -> None:
    empty = _evaluate("", target=100)
    assert empty.score == 0
    assert empty.metrics.word_count == 0
    assert [item.code for item in empty.issues] == ["empty_content"]

    assert "length_too_short" in _codes("短。", target=100)
    assert "length_too_long" in _codes("这是很长的正文。" * 20, target=10)
    assert 0 <= _evaluate("。", target=1).score <= 10


def test_repetition_sentence_uniformity_and_opening_rules_have_stable_codes() -> None:
    duplicate = "海风吹过灯塔。\n\n海风吹过灯塔。\n\n林舟记录潮线。"
    assert "duplicate_paragraph" in _codes(duplicate, target=20)

    repeated = "潮声灯影" * 30
    assert "repeated_ngram_high" in _codes(repeated, target=120)

    uniform = "甲乙丙丁。戊己庚辛。壬癸子丑。寅卯辰巳。"
    assert "uniform_sentence_lengths" in _codes(uniform, target=16)

    similar = "林舟看见远处海雾升起。\n\n林舟看见远处齿轮转动。\n\n林舟看见远处灯火熄灭。"
    assert "similar_paragraph_openings" in _codes(similar, target=40)

    varied = "潮起。林舟沿长长的螺旋楼梯走到顶层。旧钟忽然响了三次，他停下记录。"
    assert "uniform_sentence_lengths" not in _codes(varied, target=30)


def test_cliches_banned_phrases_structure_and_punctuation_are_detected() -> None:
    content = "第1章\n值得注意的是，空气中弥漫着违禁表达！！！……海雾。"
    codes = _codes(content, target=30)
    assert {
        "ai_cliche",
        "banned_phrase",
        "punctuation_overuse",
        "punctuation_anomaly",
        "embedded_heading_or_summary",
    } <= codes


def test_dialogue_and_paragraph_ratios_cover_both_extremes() -> None:
    high_dialogue = "“这是持续很久的一段对话，用来覆盖几乎整篇章节的可见字符。”" * 5
    assert "dialogue_ratio_high" in _codes(high_dialogue, target=120)

    no_dialogue = "林舟沿着螺旋楼梯检查每一级铆钉，并记录墙面潮痕的高度变化。" * 5
    assert "dialogue_ratio_low" in _codes(no_dialogue, target=150)

    short_paragraphs = "一。\n\n二。\n\n三。\n\n四。"
    assert "short_paragraphs" in _codes(short_paragraphs, target=10)

    long_paragraph = "海" * 600 + "。\n\n" + "这是另一个完整段落，用于确认长段落比例阈值。"
    assert "long_paragraph" in _codes(long_paragraph, target=620)


def test_configuration_thresholds_and_metric_values_take_effect() -> None:
    config = MechanicalEvaluationConfig(
        min_length_ratio=0.1,
        dialogue_check_min_chars=10_000,
        sentence_stddev_min=0,
        repeated_ngram_ratio_threshold=1,
    )
    result = _evaluate("第一句很短。第二句明显更长并且包含许多细节。", target=100, config=config)
    assert "length_too_short" not in {item.code for item in result.issues}
    assert result.metrics.paragraph_count == 1
    assert result.metrics.sentence_count == 2
    assert result.metrics.average_sentence_length > 0
    assert result.metrics.sentence_length_stddev > 0
    assert 0 <= result.metrics.dialogue_ratio <= 1
    assert 0 <= result.score <= 10


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" ALICE， ", "alice"),
        ("林 舟。", "林舟"),
        ("10", "10"),
        ("10.500", "10.5"),
        ("存活", "alive"),
        ("死亡", "dead"),
        ("YES", "true"),
        ("否", "false"),
    ],
)
def test_fact_normalizer_values(value: str, expected: str) -> None:
    assert FactNormalizer().normalize_object(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("located_at", "location"),
        ("is_at", "location"),
        ("carries", "possession"),
        ("possesses", "possession"),
        ("knows", "knowledge"),
        ("discovered", "knowledge"),
        ("is_alive", "alive"),
    ],
)
def test_fact_normalizer_predicate_aliases(value: str, expected: str) -> None:
    assert FactNormalizer().normalize_predicate(value) == expected


def test_fact_normalizer_is_conservative_and_retains_raw_fact() -> None:
    normalizer = FactNormalizer()
    assert normalizer.normalize_object("blue") != normalizer.normalize_object("black")
    assert normalizer.normalize_predicate("likes") != normalizer.normalize_predicate("hates")
    raw = FactEvidence(
        subject=" Alice ",
        predicate="IS_AT",
        object=" Harbor。",
        chapter_number=1,
        valid_from_chapter=1,
    )
    normalized = normalizer.normalize(raw)
    assert (normalized.subject, normalized.predicate, normalized.object) == (
        "alice",
        "location",
        "harbor",
    )
    assert normalized.raw is raw
