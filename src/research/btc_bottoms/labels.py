"""Conclusion labels for the BTC bottom study (plan section 6, verbatim).

Written as the FIRST commit of wave 2b, before any study result exists.
The rule is fixed by the pre-registered plan
(``docs/btc-bottom-study/00-plan.md`` section 6); this module must not
deviate from it.  Signature is frozen so the other analysis parts (g1's
macro overlay, g3's case files) can code against it.

Rule (plan section 6)
---------------------
- **candidate**: usable lead in at least 2 of the evaluable events of
  set A, lift >= 1.5 with >= 3 episodes, placebo add-one p_lift <= 0.10,
  sweep median lift >= 1.2, and leave-one-out keeps hit rate >= 0.5.
- **weak**: meets the hit criterion but fails the lift, placebo or
  robustness test.
- **no evidence**: anything else.
- **cannot evaluate**: fewer than 2 evaluable events.

Boundary choices (pinned by tests)
----------------------------------
Every comparison in the plan text is inclusive (">=", "<=") exactly as
written: ``n_usable_leads >= 2``, ``lift >= 1.5``, ``n_episodes >= 3``,
``placebo_p_lift <= 0.10``, ``sweep_median_lift >= 1.2``,
``loo_min_hit_rate >= 0.5``.  The plan says "at least 2" and "keeps
hit rate >= 0.5"; the tests pin the exact boundary values so a later
``>``/``<`` slip fails loudly.

NaN policy (decided here, as instructed)
----------------------------------------
Any NaN among the metric inputs (``lift``, ``placebo_p_lift``,
``sweep_median_lift``, ``loo_min_hit_rate``) returns
``"cannot evaluate"``: NaN is *missing* evidence, not failed evidence,
and "no evidence" would assert the signal showed nothing, which a NaN
does not establish.  ``n_evaluable < 2`` short-circuits to
``"cannot evaluate"`` before any NaN check, per the plan.

Never return "validated", "predictive", "proven" or "works": the label
vocabulary is closed by the plan.
"""

from __future__ import annotations

import math

__all__ = ["label"]


def label(
    n_evaluable: int,
    n_usable_leads: int,
    lift: float,
    n_episodes: int,
    placebo_p_lift: float,
    sweep_median_lift: float,
    loo_min_hit_rate: float,
) -> str:
    """Classify one signal's evidence against the plan's fixed rule.

    Parameters mirror the study engine's outputs for one signal on one
    event set: ``n_evaluable`` events with non-NaN signal coverage,
    ``n_usable_leads`` of them covered by a hit episode (on or before
    ``confirm_date``), plus lift / episode count / placebo add-one
    p_lift / sweep-median lift / leave-one-out minimum hit rate.
    """
    if n_evaluable < 2:
        return "cannot evaluate"

    metrics = (lift, placebo_p_lift, sweep_median_lift, loo_min_hit_rate)
    if any(isinstance(m, float) and math.isnan(m) for m in metrics):
        return "cannot evaluate"

    hit_criterion = n_usable_leads >= 2
    tests_pass = (
        lift >= 1.5
        and n_episodes >= 3
        and placebo_p_lift <= 0.10
        and sweep_median_lift >= 1.2
        and loo_min_hit_rate >= 0.5
    )
    if hit_criterion and tests_pass:
        return "candidate"
    if hit_criterion:
        return "weak"
    return "no evidence"
