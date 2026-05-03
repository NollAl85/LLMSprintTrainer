"""Sprint/kilo cycling constraints for LLM planning."""

from __future__ import annotations


def get_sprint_kilo_constraints() -> dict:
    """Return constraints for lifting recommendations around sprint/kilo cycling."""

    return {
        "sport_context": "cycling sprint and kilo performance",
        "primary_performance_constraint": "Protect cycling sprint quality and freshness.",
        "principles": [
            "Cycling sprint quality is the primary performance constraint.",
            "Avoid excessive lower-body eccentric volume before sprint sessions.",
            "Avoid hard leg lifting within 24-48h before key sprint sessions.",
            "Distinguish strength-maintenance lifting from hypertrophy-oriented leg volume.",
            "Prefer low-volume, high-quality strength work when sprint freshness matters.",
            "Flag leg sessions likely to interfere with 15s, 30s, or 60s cycling power.",
            "Do not create a generic bodybuilding program unless explicitly requested.",
        ],
        "timing_rules": [
            {
                "rule": "No hard lower-body lifting 24h before key sprint sessions.",
                "severity": "high",
            },
            {
                "rule": "Use caution with high-volume lower-body work 48h before key sprint sessions.",
                "severity": "medium",
            },
            {
                "rule": "Place heavier lower-body strength work after sprint quality days when possible.",
                "severity": "medium",
            },
        ],
        "fatigue_flags": [
            "High sets of squats, deadlifts, lunges, leg press, or RDLs.",
            "High eccentric emphasis or novelty likely to cause DOMS.",
            "Failure sets or drop sets for lower body near sprint days.",
            "Rapid weekly lower-body volume increases.",
        ],
        "routine_archetypes": [
            "upper-body / trunk",
            "low-volume heavy lower body",
            "posterior-chain maintenance",
            "mobility/prehab",
        ],
        "routine_generation_rules": [
            "Keep lower-body strength work low volume unless the user asks for hypertrophy.",
            "Prefer crisp heavy sets with generous rest over metabolite-heavy leg work.",
            "Use upper-body and trunk work to add training value without compromising sprint power.",
            "Call out any assumption about sprint-session timing before recommending hard leg work.",
        ],
    }
