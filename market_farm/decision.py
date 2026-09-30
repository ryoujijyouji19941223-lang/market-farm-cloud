from __future__ import annotations


def forecast_qualification(probability_up, price_score, news_score, macro_score):
    """Keep direction separate from confidence to make a forecast."""
    factors = [float(price_score), float(news_score), float(macro_score)]
    weights = [0.68, 0.17, 0.15]
    strength = sum(w * abs(v) for w, v in zip(weights, factors))

    active = [v for v in factors if abs(v) >= 0.04]
    if active:
        positive = sum(v > 0 for v in active)
        negative = sum(v < 0 for v in active)
        agreement = max(positive, negative) / len(active)
    else:
        agreement = 0.0

    direction = "UP" if probability_up >= 0.55 else ("DOWN" if probability_up <= 0.45 else "FLAT")
    qualified = strength >= 0.10 and agreement >= 0.50

    return {
        "direction": direction,
        "decision": "FORECAST" if qualified else "ABSTAIN",
        "evidence_strength": float(strength),
        "factor_agreement": float(agreement),
        "reason": None if qualified else "insufficient_evidence",
    }
