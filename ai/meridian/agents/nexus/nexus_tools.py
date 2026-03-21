from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Supported languages
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES = [
    "en", "es", "fr", "de", "pt", "zh", "ja", "ko",
    "ar", "hi", "ru", "it", "nl", "sv", "pl", "tr",
]

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CulturalProfile(BaseModel):
    """Hofstede 6-dimension cultural profile for a country."""
    country: str
    hofstede_scores: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Keys: power_distance, individualism, masculinity, "
            "uncertainty_avoidance, long_term_orientation, indulgence"
        ),
    )
    communication_style: str = "low_context"  # high_context | low_context


class CulturalAdaptation(BaseModel):
    """Cross-cultural communication recommendations."""
    source_culture: str
    target_culture: str
    adaptations: list[str] = Field(default_factory=list)
    style_recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in cultural profiles (~10 representative countries)
# Scores sourced from Hofstede Insights (approximate research values).
# ---------------------------------------------------------------------------

_CULTURAL_DATABASE: dict[str, dict[str, Any]] = {
    "united_states": {
        "hofstede_scores": {
            "power_distance": 40, "individualism": 91, "masculinity": 62,
            "uncertainty_avoidance": 46, "long_term_orientation": 26, "indulgence": 68,
        },
        "communication_style": "low_context",
    },
    "japan": {
        "hofstede_scores": {
            "power_distance": 54, "individualism": 46, "masculinity": 95,
            "uncertainty_avoidance": 92, "long_term_orientation": 88, "indulgence": 42,
        },
        "communication_style": "high_context",
    },
    "germany": {
        "hofstede_scores": {
            "power_distance": 35, "individualism": 67, "masculinity": 66,
            "uncertainty_avoidance": 65, "long_term_orientation": 83, "indulgence": 40,
        },
        "communication_style": "low_context",
    },
    "brazil": {
        "hofstede_scores": {
            "power_distance": 69, "individualism": 38, "masculinity": 49,
            "uncertainty_avoidance": 76, "long_term_orientation": 44, "indulgence": 59,
        },
        "communication_style": "high_context",
    },
    "china": {
        "hofstede_scores": {
            "power_distance": 80, "individualism": 20, "masculinity": 66,
            "uncertainty_avoidance": 30, "long_term_orientation": 87, "indulgence": 24,
        },
        "communication_style": "high_context",
    },
    "india": {
        "hofstede_scores": {
            "power_distance": 77, "individualism": 48, "masculinity": 56,
            "uncertainty_avoidance": 40, "long_term_orientation": 51, "indulgence": 26,
        },
        "communication_style": "high_context",
    },
    "sweden": {
        "hofstede_scores": {
            "power_distance": 31, "individualism": 71, "masculinity": 5,
            "uncertainty_avoidance": 29, "long_term_orientation": 53, "indulgence": 78,
        },
        "communication_style": "low_context",
    },
    "mexico": {
        "hofstede_scores": {
            "power_distance": 81, "individualism": 30, "masculinity": 69,
            "uncertainty_avoidance": 82, "long_term_orientation": 24, "indulgence": 97,
        },
        "communication_style": "high_context",
    },
    "nigeria": {
        "hofstede_scores": {
            "power_distance": 80, "individualism": 30, "masculinity": 60,
            "uncertainty_avoidance": 55, "long_term_orientation": 13, "indulgence": 84,
        },
        "communication_style": "high_context",
    },
    "australia": {
        "hofstede_scores": {
            "power_distance": 36, "individualism": 90, "masculinity": 61,
            "uncertainty_avoidance": 51, "long_term_orientation": 21, "indulgence": 71,
        },
        "communication_style": "low_context",
    },
}

HOFSTEDE_DIMENSIONS = [
    "power_distance", "individualism", "masculinity",
    "uncertainty_avoidance", "long_term_orientation", "indulgence",
]

# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def get_cultural_profile(country: str) -> CulturalProfile:
    """
    Look up a Hofstede cultural profile for a country.

    Country name is normalised to lowercase with underscores.
    Returns a default mid-range profile if the country is not in the database.
    """
    key = country.lower().replace(" ", "_").replace("-", "_")
    data = _CULTURAL_DATABASE.get(key)

    if data:
        return CulturalProfile(
            country=country,
            hofstede_scores=data["hofstede_scores"],
            communication_style=data["communication_style"],
        )

    # Default mid-range profile for unknown countries
    return CulturalProfile(
        country=country,
        hofstede_scores={dim: 50 for dim in HOFSTEDE_DIMENSIONS},
        communication_style="low_context",
    )


def adapt_communication(
    source_country: str, target_country: str
) -> CulturalAdaptation:
    """
    Generate cross-cultural communication recommendations based on
    Hofstede dimension gaps between source and target cultures.
    """
    source = get_cultural_profile(source_country)
    target = get_cultural_profile(target_country)

    adaptations = []
    style_recs = []

    for dim in HOFSTEDE_DIMENSIONS:
        s_score = source.hofstede_scores.get(dim, 50)
        t_score = target.hofstede_scores.get(dim, 50)
        gap = t_score - s_score

        if abs(gap) < 20:
            continue

        label = dim.replace("_", " ").title()
        adaptations.append(
            f"{label}: gap of {abs(gap)} points "
            f"({'higher' if gap > 0 else 'lower'} in target culture)."
        )

        rec = _dimension_recommendation(dim, gap)
        if rec:
            style_recs.append(rec)

    if not adaptations:
        adaptations.append(
            "Cultural profiles are relatively similar — minimal adaptation needed."
        )

    # Communication style adaptation
    if source.communication_style != target.communication_style:
        if target.communication_style == "high_context":
            style_recs.append(
                "Target culture favors high-context communication. "
                "Pay attention to non-verbal cues, read between the lines, "
                "and avoid being overly direct with negative feedback."
            )
        else:
            style_recs.append(
                "Target culture favors low-context communication. "
                "Be explicit, state expectations clearly, and don't "
                "rely on implied meaning."
            )

    return CulturalAdaptation(
        source_culture=source_country,
        target_culture=target_country,
        adaptations=adaptations,
        style_recommendations=style_recs,
    )


def _dimension_recommendation(dimension: str, gap: int) -> str:
    """Generate a recommendation based on a Hofstede dimension gap."""
    recs = {
        "power_distance": {
            "high": (
                "Show more deference to hierarchy and seniority. "
                "Use formal titles and allow leaders to speak first."
            ),
            "low": (
                "Adopt a more egalitarian tone. Encourage open dialogue "
                "regardless of rank and minimize formality."
            ),
        },
        "individualism": {
            "high": (
                "Emphasize personal achievement and individual accountability. "
                "Give direct, person-specific feedback."
            ),
            "low": (
                "Emphasize group harmony and collective success. "
                "Avoid singling out individuals publicly."
            ),
        },
        "masculinity": {
            "high": (
                "Frame goals in terms of competition and measurable achievement. "
                "Be decisive and results-focused."
            ),
            "low": (
                "Emphasize collaboration, quality of life, and consensus. "
                "Value work-life balance in discussions."
            ),
        },
        "uncertainty_avoidance": {
            "high": (
                "Provide more structure, detail, and clear timelines. "
                "Minimize ambiguity in plans and commitments."
            ),
            "low": (
                "Be comfortable with ambiguity and flexibility. "
                "Avoid over-structuring — leave room for adaptation."
            ),
        },
        "long_term_orientation": {
            "high": (
                "Focus on long-term strategy and future payoff. "
                "Show patience with results and value persistence."
            ),
            "low": (
                "Emphasize quick wins and present-focused benefits. "
                "Respect traditions and established practices."
            ),
        },
        "indulgence": {
            "high": (
                "Allow space for personal expression and enjoyment. "
                "Keep the tone optimistic and encouraging."
            ),
            "low": (
                "Maintain a more restrained, professional tone. "
                "Focus on duty and discipline over personal gratification."
            ),
        },
    }

    direction = "high" if gap > 0 else "low"
    dim_recs = recs.get(dimension, {})
    return dim_recs.get(direction, "")
