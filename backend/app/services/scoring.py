"""Score de confiance d'un relevé de prix (0-100).

Trois composantes :
- fraîcheur  (50 %) : demi-vie de 7 jours. Un prix en rayon change rarement
  en 72 h ; l'ancienne règle (0 % après 3 jours) jetait des prix encore bons.
- communauté (30 %) : moyenne bayésienne (confirmations + 1) / (votes + 2),
  donc 50 % sans vote, et un seul vote ne fait pas tout basculer.
- preuves    (20 %) : photo, présence GPS vérifiée en magasin.
Un relevé jugé anormal (prix très éloigné de la médiane) est divisé par 2.
"""
from datetime import datetime, timezone
import math

FRESHNESS_HALF_LIFE_DAYS = 7.0


def haversine_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def age_days(observed_at: datetime, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - observed_at).total_seconds() / 86400)


def freshness_score(observed_at: datetime, now: datetime | None = None) -> float:
    return 0.5 ** (age_days(observed_at, now) / FRESHNESS_HALF_LIFE_DAYS)


def community_score(confirmations: int, rejections: int) -> float:
    return (confirmations + 1) / (confirmations + rejections + 2)


def evidence_score(has_proof: bool, gps_verified: bool) -> float:
    return 0.4 + (0.3 if has_proof else 0.0) + (0.3 if gps_verified else 0.0)


def confidence_level(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def freshness_label(observed_at: datetime, now: datetime | None = None) -> str:
    days = age_days(observed_at, now)
    if days < 0.25:
        return "Il y a quelques heures"
    if days < 1:
        return "Aujourd'hui"
    if days < 2:
        return "Hier"
    if days < 7:
        return f"Il y a {int(days)} jours"
    if days < 14:
        return "La semaine dernière"
    if days < 60:
        return f"Il y a {int(days // 7)} semaines"
    return f"Il y a {int(days // 30)} mois"


def confidence_for(
    observed_at: datetime,
    confirmations: int,
    rejections: int,
    *,
    has_proof: bool = False,
    gps_verified: bool = False,
    flagged: bool = False,
    now: datetime | None = None,
) -> dict:
    fresh = freshness_score(observed_at, now)
    community = community_score(confirmations, rejections)
    evidence = evidence_score(has_proof, gps_verified)
    score = 0.5 * fresh + 0.3 * community + 0.2 * evidence
    if flagged:
        score *= 0.5
    score = round(score * 100, 1)
    return {
        "confidence": score,
        "confidence_level": confidence_level(score),
        "freshness": round(fresh * 100, 1),
        "community": round(community * 100, 1),
        "freshness_label": freshness_label(observed_at, now),
    }
