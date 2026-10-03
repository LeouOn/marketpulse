"""Tests for the plan-section-6 label rule (wave 2b, first commit).

Every boundary in the plan text is pinned with an exact-boundary test
so a later >= / > slip fails loudly.  NaN policy and the
n_evaluable short-circuit are pinned too.
"""

from __future__ import annotations

import math

import pytest

from src.research.btc_bottoms.labels import label


def candidate_kwargs(**overrides):
    """Inputs that make every plan test pass exactly at the boundary."""
    base = dict(
        n_evaluable=3,
        n_usable_leads=2,
        lift=1.5,
        n_episodes=3,
        placebo_p_lift=0.10,
        sweep_median_lift=1.2,
        loo_min_hit_rate=0.5,
    )
    base.update(overrides)
    return base


class TestLabel:
    def test_all_boundaries_met_is_candidate(self):
        # Exactly at every inclusive boundary from the plan text.
        assert label(**candidate_kwargs()) == "candidate"

    def test_hit_criterion_boundary_is_at_least_two(self):
        assert label(**candidate_kwargs(n_usable_leads=2)) == "candidate"
        assert label(**candidate_kwargs(n_usable_leads=1)) == "no evidence"
        assert label(**candidate_kwargs(n_usable_leads=3)) == "candidate"

    def test_lift_boundary_inclusive(self):
        assert label(**candidate_kwargs(lift=1.5)) == "candidate"
        assert label(**candidate_kwargs(lift=1.49999)) == "weak"
        assert label(**candidate_kwargs(lift=1.50001)) == "candidate"

    def test_episode_count_boundary_inclusive(self):
        assert label(**candidate_kwargs(n_episodes=3)) == "candidate"
        assert label(**candidate_kwargs(n_episodes=2)) == "weak"
        assert label(**candidate_kwargs(n_episodes=4)) == "candidate"

    def test_placebo_boundary_inclusive(self):
        assert label(**candidate_kwargs(placebo_p_lift=0.10)) == "candidate"
        assert label(**candidate_kwargs(placebo_p_lift=0.100001)) == "weak"
        assert label(**candidate_kwargs(placebo_p_lift=0.0999)) == "candidate"

    def test_sweep_median_boundary_inclusive(self):
        assert label(**candidate_kwargs(sweep_median_lift=1.2)) == "candidate"
        assert label(**candidate_kwargs(sweep_median_lift=1.1999)) == "weak"
        assert label(**candidate_kwargs(sweep_median_lift=1.3)) == "candidate"

    def test_loo_boundary_inclusive(self):
        assert label(**candidate_kwargs(loo_min_hit_rate=0.5)) == "candidate"
        assert label(**candidate_kwargs(loo_min_hit_rate=0.4999)) == "weak"
        assert label(**candidate_kwargs(loo_min_hit_rate=0.75)) == "candidate"

    def test_failing_one_test_with_hits_is_weak(self):
        # Hit criterion met, each single failure flips candidate -> weak.
        assert label(**candidate_kwargs(lift=1.0)) == "weak"
        assert label(**candidate_kwargs(placebo_p_lift=0.5)) == "weak"
        assert label(**candidate_kwargs(sweep_median_lift=1.0)) == "weak"
        assert label(**candidate_kwargs(loo_min_hit_rate=0.0)) == "weak"
        assert label(**candidate_kwargs(n_episodes=1)) == "weak"

    def test_no_hits_is_no_evidence_even_with_great_metrics(self):
        assert label(**candidate_kwargs(n_usable_leads=0)) == "no evidence"
        assert label(**candidate_kwargs(n_usable_leads=1, lift=99.0)) == "no evidence"

    def test_fewer_than_two_evaluable_shortcircuits(self):
        for n in (0, 1):
            assert label(**candidate_kwargs(n_evaluable=n)) == "cannot evaluate"
        # Short-circuit even with NaN metrics (plan order: n_evaluable first).
        assert (
            label(
                n_evaluable=1,
                n_usable_leads=1,
                lift=math.nan,
                n_episodes=3,
                placebo_p_lift=0.05,
                sweep_median_lift=2.0,
                loo_min_hit_rate=1.0,
            )
            == "cannot evaluate"
        )
        assert label(**candidate_kwargs(n_evaluable=2)) == "candidate"

    def test_nan_metric_is_cannot_evaluate_when_hits_exist(self):
        # NaN is missing evidence only when the hit criterion is met
        # (the tests cannot be applied); documented choice.
        for key in ("lift", "placebo_p_lift", "sweep_median_lift", "loo_min_hit_rate"):
            assert label(**candidate_kwargs(**{key: math.nan})) == "cannot evaluate"

    def test_nan_metrics_with_no_hits_is_no_evidence(self):
        # Hit criterion is evaluated FIRST: a never-firing signal (0
        # episodes, NaN lift) is an informative absence -> no evidence,
        # not missing evidence.
        assert label(**candidate_kwargs(lift=math.nan, n_usable_leads=0)) == "no evidence"
        assert label(**candidate_kwargs(lift=math.nan, n_usable_leads=1)) == "no evidence"
        assert label(**candidate_kwargs(lift=math.nan, placebo_p_lift=math.nan, n_usable_leads=1)) == "no evidence"

    def test_vocabulary_is_closed(self):
        """The function can only speak the four plan labels."""
        allowed = {"candidate", "weak", "no evidence", "cannot evaluate"}
        probes = [
            candidate_kwargs(),
            candidate_kwargs(n_usable_leads=0),
            candidate_kwargs(lift=0.0),
            candidate_kwargs(n_evaluable=0),
            candidate_kwargs(lift=math.nan),
        ]
        assert {label(**p) for p in probes} <= allowed

    @pytest.mark.parametrize("n_evaluable", [2, 3, 7])
    def test_two_or_more_evaluable_is_evaluable(self, n_evaluable):
        assert label(**candidate_kwargs(n_evaluable=n_evaluable)) == "candidate"
