"""Offline tests for ``src/llm/system_prompts.py``.

Pure text assembly: every prompt builder is exercised with normal, missing and
odd inputs (braces in values, plain-string chunks, numpy values, NaN/inf),
asserting no unreplaced ``{PLACEHOLDER}`` leaks and that results are stable
strings. No LLM, no RAG, no network.
"""

from __future__ import annotations

import numpy as np

from src.llm.system_prompts import (
    CHART_ANALYSIS_PROMPT,
    DATA_VALIDATION_PROMPT,
    HYPOTHESIS_TESTING_PROMPT,
    MARKET_ANALYSIS_PROMPT,
    TRADE_REVIEW_PROMPT,
    TRADING_ANALYST_BASE,
    build_enhanced_prompt,
    get_system_prompt,
)

PLACEHOLDER_TOKENS = [
    "{CONTEXT_INJECTION}",
    "{HYPOTHESIS_INJECTION}",
    "{DATA_INJECTION}",
    "{HYPOTHESIS_TEXT}",
    "{DATA_SUMMARY}",
    "{MARKET_DATA}",
    "{CHART_DATA}",
    "{DATA_TO_VALIDATE}",
    "{TRADE_CONTEXT}",
    "{MARKET_CONDITIONS}",
]

ALL_TEMPLATES = {
    "trading_analyst": TRADING_ANALYST_BASE,
    "hypothesis_testing": HYPOTHESIS_TESTING_PROMPT,
    "market_analysis": MARKET_ANALYSIS_PROMPT,
    "chart_analysis": CHART_ANALYSIS_PROMPT,
    "data_validation": DATA_VALIDATION_PROMPT,
    "trade_review": TRADE_REVIEW_PROMPT,
}

MARKET_DATA = {"btc_perp": {"price": 45000.5, "change_24h": 2.5}}


def _chunks(*contents, type_=None):
    out = []
    for c in contents:
        chunk = {"content": c}
        if type_:
            chunk["type"] = type_
        out.append(chunk)
    return out


# ---------------------------------------------------------------------------
# get_system_prompt: registry shape consumers use
# ---------------------------------------------------------------------------


def test_get_system_prompt_maps_every_documented_type():
    for prompt_type, template in ALL_TEMPLATES.items():
        assert get_system_prompt(prompt_type) is template


def test_get_system_prompt_defaults_and_bad_input():
    assert get_system_prompt() is TRADING_ANALYST_BASE  # default arg
    assert get_system_prompt("no_such_type") is TRADING_ANALYST_BASE
    assert get_system_prompt("") is TRADING_ANALYST_BASE
    assert get_system_prompt(None) is TRADING_ANALYST_BASE


# ---------------------------------------------------------------------------
# build_enhanced_prompt: normal assembly
# ---------------------------------------------------------------------------


def test_context_chunks_are_injected_as_knowledge():
    result = build_enhanced_prompt(TRADING_ANALYST_BASE, _chunks("fact one", "fact two"), query="bias?")

    assert "RELEVANT CONTEXT:" in result
    assert "**Relevant Knowledge:**\nfact one" in result
    assert "**Relevant Knowledge:**\nfact two" in result
    # Placeholders themselves never leak.
    for token in PLACEHOLDER_TOKENS:
        assert token not in result


def test_hypothesis_chunks_are_highlighted_for_hypothesis_queries():
    chunks = _chunks("generic fact") + _chunks("the cascade hypothesis", type_="tested_hypothesis")

    # TRADING_ANALYST_BASE carries the {HYPOTHESIS_INJECTION} and {DATA_INJECTION} slots.
    result = build_enhanced_prompt(TRADING_ANALYST_BASE, chunks, query="test the cascade", market_data=MARKET_DATA)

    assert "ACTIVE HYPOTHESIS:" in result
    assert "the cascade hypothesis" in result
    # Market data lands in the data slot.
    assert '"btc_perp"' in result
    for token in PLACEHOLDER_TOKENS:
        assert token not in result

    # The query itself is placed at {HYPOTHESIS_TEXT} in the testing template.
    testing = build_enhanced_prompt(
        HYPOTHESIS_TESTING_PROMPT, chunks, query="test the cascade", market_data=MARKET_DATA
    )
    assert "test the cascade" in testing
    assert '"btc_perp"' in testing


def test_hypothesis_injection_requires_hypothesis_word_in_query():
    chunks = _chunks("the cascade hypothesis", type_="tested_hypothesis")

    result = build_enhanced_prompt(TRADING_ANALYST_BASE, chunks, query="what is the bias?")

    assert "ACTIVE HYPOTHESIS:" not in result


def test_missing_inputs_produce_placeholder_free_prompts():
    # No chunks, no query, no data at all.
    for template in ALL_TEMPLATES.values():
        result = build_enhanced_prompt(template, [], query="", market_data=None)

        for token in PLACEHOLDER_TOKENS:
            assert token not in result
        assert isinstance(result, str) and result  # stable non-empty string


def test_empty_market_data_dict_is_treated_as_no_data():
    result = build_enhanced_prompt(MARKET_ANALYSIS_PROMPT, [], market_data={})

    assert "No market data provided" in result


def test_every_template_assembles_without_leftover_placeholders():
    queries = ["", "what is the bias?", "test the overnight hypothesis"]
    datas = [None, MARKET_DATA]

    for template in ALL_TEMPLATES.values():
        for query in queries:
            for data in datas:
                result = build_enhanced_prompt(template, _chunks("ctx"), query=query, market_data=data)
                for token in PLACEHOLDER_TOKENS:
                    assert token not in result, f"{token} leaked for query={query!r} data={data!r}"


def test_results_are_deterministic():
    a = build_enhanced_prompt(HYPOTHESIS_TESTING_PROMPT, _chunks("x"), query="q", market_data=MARKET_DATA)
    b = build_enhanced_prompt(HYPOTHESIS_TESTING_PROMPT, _chunks("x"), query="q", market_data=MARKET_DATA)

    assert a == b


# ---------------------------------------------------------------------------
# Odd values: braces must survive verbatim
# ---------------------------------------------------------------------------


def test_braces_in_values_are_not_interpreted():
    braces_data = {"formula": "{price} * 2", "tpl": "{{not_a_placeholder}}"}

    # TRADING_ANALYST_BASE carries the {CONTEXT_INJECTION} slot for the chunk.
    result = build_enhanced_prompt(
        TRADING_ANALYST_BASE, _chunks("chunk with {BRACES} inside"), query="q", market_data=braces_data
    )

    # Braces from the data and the context chunk survive untouched.
    assert "{price} * 2" in result
    assert "{{not_a_placeholder}}" in result
    assert "chunk with {BRACES} inside" in result


def test_placeholder_tokens_inside_injected_values_stay_literal():
    """A query containing '{MARKET_CONDITIONS}' must not have market data
    re-expanded into it by a later replacement pass."""
    result = build_enhanced_prompt(
        TRADE_REVIEW_PROMPT, [], query="watch the {MARKET_CONDITIONS} token", market_data=MARKET_DATA
    )

    # The template's own slot got the data exactly once...
    assert result.count('"btc_perp"') == 1
    # ...and the token that came from the query survives verbatim.
    assert "watch the {MARKET_CONDITIONS} token" in result


# ---------------------------------------------------------------------------
# Odd chunk shapes
# ---------------------------------------------------------------------------


def test_plain_string_chunks_are_supported():
    """The content fallback (``chunk.get('content', chunk)``) clearly intends
    plain strings to work; the old code crashed with AttributeError."""
    result = build_enhanced_prompt(TRADING_ANALYST_BASE, ["plain string chunk"], query="bias?")

    assert "plain string chunk" in result
    assert "RELEVANT CONTEXT:" in result


def test_mixed_string_and_dict_chunks():
    chunks = ["plain chunk", {"content": "dict chunk"}, {"type": "other"}]

    result = build_enhanced_prompt(TRADING_ANALYST_BASE, chunks, query="bias?")

    assert "plain chunk" in result
    assert "dict chunk" in result


def test_hypothesis_chunk_without_content_key_does_not_crash():
    chunks = [{"type": "tested_hypothesis"}]

    result = build_enhanced_prompt(TRADING_ANALYST_BASE, chunks, query="test this hypothesis")

    assert "ACTIVE HYPOTHESIS:" in result  # present, with empty text


# ---------------------------------------------------------------------------
# Odd market_data values: numpy, NaN/inf, nested junk
# ---------------------------------------------------------------------------


def test_numpy_values_in_market_data_are_serialised():
    data = {"volume": np.int64(12345), "prices": np.float64(45000.5), "flags": np.array([1, 2, 3])}

    result = build_enhanced_prompt(MARKET_ANALYSIS_PROMPT, [], market_data=data)

    assert "12345" in result
    assert "45000.5" in result


def test_nan_and_inf_values_do_not_crash():
    data = {"x": float("nan"), "y": float("inf")}

    result = build_enhanced_prompt(CHART_ANALYSIS_PROMPT, [], market_data=data)

    assert isinstance(result, str)
    # Values stringify deterministically (json's NaN/Infinity literals).
    assert "NaN" in result
    assert "Infinity" in result


def test_none_market_data_uses_the_no_data_wording():
    result = build_enhanced_prompt(CHART_ANALYSIS_PROMPT, [], market_data=None)

    assert "No chart data provided" in result


# ---------------------------------------------------------------------------
# DATA_VALIDATION_PROMPT: the JSON example must use single braces
# ---------------------------------------------------------------------------


def test_data_validation_json_example_has_single_braces():
    """The template was written with str.format-style {{ escaping, but the
    builder uses plain token replacement -- the doubled braces leaked verbatim
    into the prompt."""
    prompt = get_system_prompt("data_validation")

    assert "{{" not in prompt
    assert "}}" not in prompt
    assert '"is_valid": boolean' in prompt


def test_data_validation_prompt_assembles_with_real_data():
    result = build_enhanced_prompt(DATA_VALIDATION_PROMPT, [], market_data={"rows": 3})

    assert '"is_valid": boolean' in result
    assert '"rows": 3' in result
    for token in PLACEHOLDER_TOKENS:
        assert token not in result
