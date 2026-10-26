"""Trust score (Phase 3 of the Agent Trust Signals plan).

Pure function, no DB access — operates on the agent dict already assembled
by Phase 1 (category) and Phase 2 (signals) in api/index.py. Zero new
queries: everything this needs has already been fetched by the time it
would run.

Design: uptime is NOT one more additive component. An earlier version blended
Presence/Reliability(including uptime)/Corroboration additively, which meant
an agent with a complete profile but catastrophic uptime could never score
below roughly (100 - uptime's weight)% - because the other components had
nothing to do with whether the agent actually works, and additive buckets
can't express "this disqualifies everything else." Verified against a test
case: a 200-day-old, fully-complete, 5%-uptime agent scored 50.1/100 under
the additive design - indistinguishable from "working about half the time,"
which is exactly wrong.

Instead:
    base_score = average(Presence, Consistency, Corroboration)
    final_score = base_score * uptime_factor

uptime_factor is a multiplier in [0, 1] derived from uptime, so bad uptime
drags the ENTIRE score down proportionally rather than just costing one
slice of it. The same 5%-uptime test case now scores 18.6 - clearly "don't
trust this," not "roughly half-decent."

Every sub-score is returned alongside the raw inputs that produced it — no
black box. Nothing here is final; constants are named so they can be
retuned without touching the scoring logic itself.
"""

from __future__ import annotations

import math

# base_score is an equal-thirds average of these three.
_LEG_WEIGHT = 1.0 / 3.0  # "leg" = one of the three base_score components

# An agent reaches full longevity credit at this age; partial credit before.
_LONGEVITY_FULL_CREDIT_DAYS = 90

# Stability is scored on churn rate (card changes per 30 days), not a raw
# count, so a long-lived agent with a handful of changes isn't punished the
# same as a brand-new agent rewriting itself constantly. Each "change per
# 30 days" costs this many points.
_STABILITY_POINTS_PER_CHANGE_PER_30D = 8.0

# Consistency = Longevity + Stability, blended in this ratio (unchanged from
# the earlier design's relative balance between the two).
_LONGEVITY_SHARE_OF_CONSISTENCY = 0.6
_STABILITY_SHARE_OF_CONSISTENCY = 0.4

# No external popularity data at all (not every source tracks it) is
# neutral, not punitive — absence of stars isn't evidence of distrust.
_NEUTRAL_CORROBORATION_SCORE = 50.0

# No crawl history yet (brand-new agent): give the benefit of the doubt
# rather than treating "unproven" the same as either "proven reliable" (1.0)
# or "proven broken" (near 0). Confirmed with Manuel: 0.75 is the right
# instinct for this.
_NEUTRAL_UPTIME_MULTIPLIER = 0.75


def _sanity_check_weights() -> None:
    leg_total = _LEG_WEIGHT * 3
    assert abs(leg_total - 1.0) < 1e-9, f"base_score legs must sum to 1.0, got {leg_total}"
    consistency_total = _LONGEVITY_SHARE_OF_CONSISTENCY + _STABILITY_SHARE_OF_CONSISTENCY
    assert abs(consistency_total - 1.0) < 1e-9, (
        f"consistency shares must sum to 1.0, got {consistency_total}"
    )


_sanity_check_weights()


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _score_presence(agent: dict) -> dict:
    checks = {
        "has_description": bool((agent.get("description") or "").strip()),
        "has_skills": bool(agent.get("skills")),
        "has_base_url": bool((agent.get("base_url") or "").strip()),
        "is_categorized": (agent.get("category") or "other") != "other",
    }
    passed = sum(1 for v in checks.values() if v)
    score = _clamp(100.0 * passed / len(checks))
    return {"score": round(score, 1), "checks": checks}


def _score_consistency(signals: dict) -> dict:
    age_days = signals.get("age_days") or 0
    longevity_score = _clamp(100.0 * age_days / _LONGEVITY_FULL_CREDIT_DAYS)

    card_change_count = signals.get("card_change_count") or 0
    effective_age_days = max(age_days, 1)  # avoid division by zero for day-0 agents
    changes_per_30d = card_change_count / effective_age_days * 30
    stability_score = _clamp(100.0 - changes_per_30d * _STABILITY_POINTS_PER_CHANGE_PER_30D)

    consistency_score = _clamp(
        longevity_score * _LONGEVITY_SHARE_OF_CONSISTENCY
        + stability_score * _STABILITY_SHARE_OF_CONSISTENCY
    )

    return {
        "score": round(consistency_score, 1),
        "longevity": {"score": round(longevity_score, 1), "age_days": age_days},
        "stability": {
            "score": round(stability_score, 1),
            "card_change_count": card_change_count,
            "changes_per_30d": round(changes_per_30d, 2),
        },
    }


def _score_corroboration(signals: dict) -> dict:
    popularity = signals.get("external_popularity") or {}

    if not popularity:
        score = _NEUTRAL_CORROBORATION_SCORE
    else:
        stars = popularity.get("github_stars") or 0
        likes = popularity.get("hf_likes") or 0
        # log1p scaling: a handful of stars isn't dismissed, but a viral
        # 10,000-star repo doesn't blow past the cap either. Modest ceiling
        # since this bucket is known-weak — agents aren't deduped across
        # sources yet (see Phase 2 notes), so this only reflects known
        # popularity metrics, not real multi-source corroboration.
        signal_strength = math.log1p(max(stars, 0) + max(likes, 0))
        score = _clamp(_NEUTRAL_CORROBORATION_SCORE + signal_strength * 10.0)

    return {
        "score": round(score, 1),
        "external_popularity": popularity or None,
    }


def _uptime_factor(signals: dict) -> dict:
    uptime_pct = signals.get("uptime_pct")
    uptime_sample_size = signals.get("uptime_sample_size") or 0
    has_data = uptime_pct is not None and uptime_sample_size > 0

    if not has_data:
        factor = _NEUTRAL_UPTIME_MULTIPLIER
    else:
        # Square root softens the drop for "degraded but working" agents
        # (60% uptime -> 0.77, not 0.60) while still letting genuinely
        # broken agents (5% uptime -> 0.22) collapse hard.
        factor = math.sqrt(_clamp(float(uptime_pct)) / 100.0)

    return {
        "factor": round(factor, 3),
        "uptime_pct": uptime_pct,
        "sample_size": uptime_sample_size,
        "has_data": has_data,
    }


def compute_trust(agent: dict) -> dict:
    """Compute the overall trust score for one agent dict (as assembled by
    GET /agents/{id} or the MCP get_agent tool, after Phase 2's `signals`
    have been attached). Deterministic, no I/O, does not mutate `agent`."""
    signals = agent.get("signals") or {}

    presence = _score_presence(agent)
    consistency = _score_consistency(signals)
    corroboration = _score_corroboration(signals)
    uptime = _uptime_factor(signals)

    base_score = _clamp(
        presence["score"] * _LEG_WEIGHT
        + consistency["score"] * _LEG_WEIGHT
        + corroboration["score"] * _LEG_WEIGHT
    )
    final_score = _clamp(base_score * uptime["factor"])

    return {
        "score": round(final_score, 1),
        "breakdown": {
            "base_score": round(base_score, 1),
            "presence": {**presence, "weight": _LEG_WEIGHT},
            "consistency": {**consistency, "weight": _LEG_WEIGHT},
            "corroboration": {**corroboration, "weight": _LEG_WEIGHT},
            "uptime": uptime,
        },
    }
