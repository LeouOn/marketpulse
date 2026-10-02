"""Offline tests for ``src/llm/hypothesis_tester.py``.

No network, no provider, no local LLM: the client and the knowledge RAG are
fakes, and the hypotheses directory is pointed at a tmp_path. These pin the
real parsing/evaluation logic: markdown loading, the two analysis paths
(function-calling and regex fallback), status/confidence extraction, listing
and archiving.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.llm.hypothesis_tester import HypothesisTester, HypothesisTestResult

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRAG:
    """Records queries; returns one knowledge chunk like the real RAG."""

    def __init__(self):
        self.queries: list[str] = []

    def retrieve_context(self, query: str, max_results: int = 5) -> list[dict]:
        self.queries.append(query)
        return [{"type": "tested_hypothesis", "content": "knowledge chunk"}]


class _CompletionClient:
    """LLM client without ``generate_with_tools`` (plain-completion only)."""

    def __init__(self, content: str = "analysis text"):
        self.content = content
        self.calls: list[dict] = []

    async def generate_completion(self, **kwargs) -> dict | None:
        self.calls.append(kwargs)
        return {"choices": [{"message": {"content": self.content}}]}


class _ToolClient(_CompletionClient):
    """LLM client with function calling, like DeepSeekClient/ModelRouter."""

    def __init__(self, content: str = "", tool_args: dict | None = None, error: Exception | None = None):
        super().__init__(content)
        self.tool_args = tool_args
        self.error = error
        self.tool_calls: list[dict] = []

    async def generate_with_tools(self, **kwargs):
        self.tool_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.tool_args is not None:
            await kwargs["tool_handler"]("submit_hypothesis_result", self.tool_args)
        return {"choices": [{"message": {"content": self.content}}]}


# ---------------------------------------------------------------------------
# Markdown fixtures: the format _parse_hypothesis_md documents (clean) and the
# format the real files in trading_knowledge/hypotheses/active actually use.
# ---------------------------------------------------------------------------

CLEAN_MD = """# Overnight Margin Cascade Hypothesis

Some preamble text.

## Hypothesis Statement
On green days in crypto perpetuals, there may be a selloff cascade around 00:00 UTC.

## Background
Traditional equity markets have overnight margin requirements.

## Mechanism
Forced deleveraging triggers stops.

## What to Look For
- Timing: selloff begins 15-30 minutes before 00:00 UTC
* Volume spike 2-3x normal
1. Recovery bounce after window

## Testing Criteria
**Time Window:** 30
**Min Samples:** 100
**Effect Size:** 0.5
**Thresholds:**
- p < 0.05
- effect in >60% of days

## Data Requirements
- Instruments: BTC-PERP, ETH-PERP
- Timeframe: 5-minute bars
- Features: funding_rate, open_interest
- Control: random 30-minute windows

## Success Metrics
- Volume spike correlation
- Significant price movement

## Related Concepts
- Funding rate pressure

## Confounding Factors
- Exchange maintenance windows
"""

REAL_FORMAT_MD = """# Overnight Margin Cascade Hypothesis

## Hypothesis Statement
On green days in crypto perpetuals, there may be a selloff cascade around margin times.

## Testing Criteria

### Statistical Requirements
- **Sample Size**: Minimum 90 days of data
- **Significance**: p-value < 0.05 for effect detection

### Data Requirements
- **Instruments**: BTC-PERP, ETH-PERP (Binance, Bybit)
- **Timeframe**: 1-minute data around 00:00 UTC
- **Features**: Price, volume, CVD
- **Control**: Compare to random 30-minute windows

### Success Metrics
1. **Primary**: Statistically significant price movement during margin window
2. **Secondary**: Volume spike correlation with price movement
"""


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def tester(tmp_path: Path) -> HypothesisTester:
    t = HypothesisTester(_CompletionClient(), knowledge_rag=_FakeRAG())
    t.hypotheses_dir = tmp_path / "hypotheses"
    (t.hypotheses_dir / "active").mkdir(parents=True)
    return t


def _write(tester: HypothesisTester, subdir: str, name: str, md: str) -> None:
    path = tester.hypotheses_dir / subdir / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding="utf-8")


SAMPLE_DATA = {"btc_perp": {"price": 45000, "change_24h": 2.5}}


# ---------------------------------------------------------------------------
# load_hypothesis / markdown parsing
# ---------------------------------------------------------------------------


def test_load_parses_all_documented_sections(tester):
    _write(tester, "active", "cascade", CLEAN_MD)

    hyp = tester.load_hypothesis("cascade")

    assert hyp is not None
    assert hyp["name"] == "cascade"
    assert hyp["status"] == "active"
    assert hyp["description"] == "On green days in crypto perpetuals, there may be a selloff cascade around 00:00 UTC."
    assert hyp["background"].startswith("Traditional equity")
    assert hyp["mechanism"].startswith("Forced deleveraging")
    assert hyp["what_to_look_for"] == [
        "Timing: selloff begins 15-30 minutes before 00:00 UTC",
        "Volume spike 2-3x normal",
        "Recovery bounce after window",
    ]
    assert hyp["testing_criteria"]["time_window"] == 30
    assert hyp["testing_criteria"]["min_samples"] == 100
    assert hyp["testing_criteria"]["effect_size"] == 0.5
    assert hyp["data_requirements"]["instruments"] == ["BTC-PERP", "ETH-PERP"]
    assert hyp["data_requirements"]["timeframe"] == "5-minute bars"
    assert hyp["data_requirements"]["features"] == ["funding_rate", "open_interest"]
    assert hyp["data_requirements"]["control"] == "random 30-minute windows"
    assert hyp["success_metrics"] == ["Volume spike correlation", "Significant price movement"]
    assert hyp["related_concepts"] == ["Funding rate pressure"]
    assert hyp["confounding_factors"] == ["Exchange maintenance windows"]
    assert hyp["raw_content"] == CLEAN_MD


def test_criteria_lists_do_not_leak_an_empty_first_entry(tester):
    # "**Thresholds:**" has an empty value followed by bullets: the list must
    # start with the first bullet, not an empty string.
    _write(tester, "active", "cascade", CLEAN_MD)

    hyp = tester.load_hypothesis("cascade")

    assert hyp["testing_criteria"]["thresholds"] == ["p < 0.05", "effect in >60% of days"]


def test_load_parses_the_real_file_format(tester):
    """The shipped hypothesis files nest Data Requirements / Success Metrics as
    ### subsections with '- **Key**: value' bullets -- they must still parse."""
    _write(tester, "active", "overnight_margin_cascade", REAL_FORMAT_MD)

    hyp = tester.load_hypothesis("overnight_margin_cascade")

    assert hyp["testing_criteria"]["sample_size"] == "Minimum 90 days of data"
    assert hyp["testing_criteria"]["significance"] == "p-value < 0.05 for effect detection"
    # Parenthetical exchanges must not leak into the instrument list.
    assert hyp["data_requirements"]["instruments"] == ["BTC-PERP", "ETH-PERP"]
    assert hyp["data_requirements"]["timeframe"] == "1-minute data around 00:00 UTC"
    assert hyp["data_requirements"]["control"] == "Compare to random 30-minute windows"
    assert len(hyp["success_metrics"]) == 2
    assert "Statistically significant price movement" in hyp["success_metrics"][0]


def test_load_prefers_active_over_tested(tester):
    _write(tester, "tested", "cascade", CLEAN_MD)
    _write(tester, "active", "cascade", REAL_FORMAT_MD)

    hyp = tester.load_hypothesis("cascade")

    assert hyp["status"] == "active"


def test_load_falls_back_to_tested_dir(tester):
    _write(tester, "tested", "cascade", CLEAN_MD)

    hyp = tester.load_hypothesis("cascade")

    assert hyp is not None
    assert hyp["status"] == "tested"


def test_load_missing_hypothesis_returns_none(tester):
    assert tester.load_hypothesis("does_not_exist") is None


# ---------------------------------------------------------------------------
# list / archive
# ---------------------------------------------------------------------------


def test_list_hypotheses_covers_both_dirs(tester):
    _write(tester, "active", "one", CLEAN_MD)
    _write(tester, "tested", "two", CLEAN_MD)

    listed = tester.list_hypotheses()

    names = {(h["name"], h["status"]) for h in listed}
    assert ("one", "active") in names
    assert ("two", "tested") in names


def test_archive_moves_active_to_tested(tester):
    _write(tester, "active", "cascade", CLEAN_MD)

    assert tester.archive_hypothesis("cascade") is True
    assert not (tester.hypotheses_dir / "active" / "cascade.md").exists()
    assert (tester.hypotheses_dir / "tested" / "cascade.md").exists()
    # Nothing left to move.
    assert tester.archive_hypothesis("cascade") is False


def test_archive_missing_hypothesis_returns_false(tester):
    assert tester.archive_hypothesis("never_existed") is False


# ---------------------------------------------------------------------------
# test_hypothesis: the three workflows
# ---------------------------------------------------------------------------


async def test_missing_hypothesis_returns_an_error_result(tester):
    result = await tester.test_hypothesis("does_not_exist")

    assert isinstance(result, HypothesisTestResult)
    assert result.status == "error"
    assert result.confidence == 0
    assert "does_not_exist" in result.summary


async def test_without_data_returns_a_clarified_result(tester):
    _write(tester, "active", "cascade", CLEAN_MD)
    tester.llm_client.content = "A clarified, structured hypothesis."

    result = await tester.test_hypothesis("cascade")

    assert result.status == "clarified"
    assert result.confidence == 50
    assert result.raw_analysis == "A clarified, structured hypothesis."
    assert tester.knowledge_rag.queries  # RAG consulted for context
    assert tester.llm_client.calls[0]["model"] == "deep_analysis"


async def test_structured_output_builds_the_result(tester):
    _write(tester, "active", "cascade", CLEAN_MD)
    tool_client = _ToolClient(
        tool_args={
            "status": "confirmed",
            "confidence": 85,
            "summary": "The window effect is real.",
            "key_findings": ["Volume spiked 2.3x"],
            "statistical_evidence": {"p_value": 0.03},
            "trading_implications": "Fade the pre-midnight push.",
            "further_testing_needed": ["Out-of-sample window"],
        }
    )
    tester.llm_client = tool_client

    result = await tester.test_hypothesis("cascade", SAMPLE_DATA)

    assert result.status == "confirmed"
    assert result.confidence == 85
    assert result.summary == "The window effect is real."
    assert result.key_findings == ["Volume spiked 2.3x"]
    assert result.statistical_evidence == {"p_value": 0.03}
    assert result.trading_implications == "Fade the pre-midnight push."
    assert result.further_testing_needed == ["Out-of-sample window"]
    assert json.loads(result.raw_analysis)["status"] == "confirmed"
    # The tool offered to the model is the documented submit_hypothesis_result.
    tools = tool_client.tool_calls[0]["tools"]
    assert [t["function"]["name"] for t in tools] == ["submit_hypothesis_result"]


async def test_structured_output_applies_defaults_for_missing_fields(tester):
    _write(tester, "active", "cascade", CLEAN_MD)
    tester.llm_client = _ToolClient(tool_args={"summary": "Partial submission."})

    result = await tester.test_hypothesis("cascade", SAMPLE_DATA)

    assert result.status == "inconclusive"
    assert result.confidence == 50
    assert result.key_findings == []
    assert result.summary == "Partial submission."


async def test_structured_confidence_is_clamped_to_the_documented_range(tester):
    _write(tester, "active", "cascade", CLEAN_MD)
    tester.llm_client = _ToolClient(tool_args={"status": "confirmed", "confidence": 250})

    result = await tester.test_hypothesis("cascade", SAMPLE_DATA)

    assert result.confidence == 100

    tester.llm_client = _ToolClient(tool_args={"status": "confirmed", "confidence": -30})
    result = await tester.test_hypothesis("cascade", SAMPLE_DATA)
    assert result.confidence == 0


async def test_client_without_tool_support_uses_the_regex_fallback(tester):
    _write(tester, "active", "cascade", CLEAN_MD)
    tester.llm_client = _CompletionClient(
        "The evidence confirms the cascade with 85% confidence.\n- Volume spiked 2.3x\np-value was 0.03"
    )

    result = await tester.test_hypothesis("cascade", SAMPLE_DATA)

    assert result.status == "confirmed"
    assert result.confidence == 85
    assert result.key_findings == ["Volume spiked 2.3x"]
    assert "p-value" in result.statistical_evidence.get("statistical_note", "")
    assert result.raw_analysis.startswith("The evidence confirms")


async def test_tool_error_falls_back_to_the_completion_path(tester):
    _write(tester, "active", "cascade", CLEAN_MD)
    tester.llm_client = _ToolClient(error=RuntimeError("provider 500"), content="The data refutes the cascade.")

    result = await tester.test_hypothesis("cascade", SAMPLE_DATA)

    assert result.status == "refuted"
    assert result.raw_analysis == "The data refutes the cascade."


async def test_model_that_skips_the_tool_is_regex_parsed(tester):
    _write(tester, "active", "cascade", CLEAN_MD)
    tester.llm_client = _ToolClient(content="The analysis supports the cascade hypothesis.")

    result = await tester.test_hypothesis("cascade", SAMPLE_DATA)

    assert result.status == "confirmed"
    assert result.summary == "The analysis supports the cascade hypothesis."


# ---------------------------------------------------------------------------
# _parse_analysis_results: status and confidence extraction
# ---------------------------------------------------------------------------


def _parse(tester: HypothesisTester, analysis: str) -> HypothesisTestResult:
    return tester._parse_analysis_results("cascade", analysis, SAMPLE_DATA)


def test_confidence_prefers_the_percent_number_over_earlier_digits(tester):
    # "Based on 250 samples" must not become 250% confidence.
    result = _parse(tester, "Based on 250 samples, we are confident at 90%.")

    assert result.confidence == 90


def test_confidence_without_percent_marker_still_uses_the_first_number(tester):
    assert _parse(tester, "Confidence: 85").confidence == 85


def test_confidence_is_clamped_to_0_100(tester):
    assert _parse(tester, "Confidence: 300 after 300 days").confidence == 100
    assert _parse(tester, "Confidence: -5 effectively zero").confidence == 0


def test_negated_confirm_words_do_not_report_confirmed(tester):
    # Old code matched the substring "support" and reported "confirmed".
    result = _parse(tester, "The data does not support the cascade hypothesis.")

    assert result.status == "inconclusive"


def test_negated_refute_words_do_not_report_refuted(tester):
    result = _parse(tester, "The evidence fails to reject the cascade hypothesis.")

    assert result.status != "refuted"


def test_refute_word_still_wins_within_a_line(tester):
    result = _parse(tester, "The evidence refutes the cascade hypothesis.")

    assert result.status == "refuted"
    assert result.summary == "The evidence refutes the cascade hypothesis."


def test_confirm_word_sets_confirmed_and_summary(tester):
    result = _parse(tester, "The window effect is validated by the data.")

    assert result.status == "confirmed"
    assert result.summary == "The window effect is validated by the data."


def test_high_confidence_without_status_words_becomes_likely_confirmed(tester):
    result = _parse(tester, "The sample shows a strong effect. Confidence: 85")

    assert result.status == "likely_confirmed"


def test_low_confidence_without_status_words_becomes_likely_refuted(tester):
    result = _parse(tester, "The sample shows almost nothing. Confidence: 10")

    assert result.status == "likely_refuted"


def test_plain_analysis_stays_inconclusive_at_mid_confidence(tester):
    result = _parse(tester, "Some observations were made. Confidence: 50")

    assert result.status == "inconclusive"
    assert result.summary == "Analysis completed"


def test_statistical_lines_are_recorded_as_evidence(tester):
    result = _parse(tester, "The p-value was 0.03 and significance held.")

    assert "p-value" in result.statistical_evidence["statistical_note"]


def test_bullets_become_key_findings(tester):
    result = _parse(tester, "* first finding\n- second finding")

    assert result.key_findings == ["first finding", "second finding"]


# ---------------------------------------------------------------------------
# HypothesisTestResult serialization
# ---------------------------------------------------------------------------


def test_result_roundtrips_through_dict_and_json():
    result = HypothesisTestResult(
        hypothesis_name="cascade",
        timestamp="2026-10-02T00:00:00",
        status="confirmed",
        confidence=85,
        summary="s",
        key_findings=["f"],
        statistical_evidence={"p": 0.03},
        trading_implications="t",
        further_testing_needed=["x"],
        raw_analysis="raw",
    )

    assert result.to_dict()["status"] == "confirmed"
    assert json.loads(result.to_json())["confidence"] == 85


async def test_failed_llm_completion_reports_failure_text(tester):
    _write(tester, "active", "cascade", CLEAN_MD)

    async def _none(**kwargs):
        return None

    tester.llm_client.generate_completion = _none

    result = await tester.test_hypothesis("cascade")

    assert result.raw_analysis == "Failed to get clarification from LLM"
