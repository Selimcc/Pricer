from datetime import datetime, timezone
import math


def haversine_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def confidence_for(observed_at, confirmations, rejections):
    age_hours = max(0.0, (datetime.now(timezone.utc) - observed_at).total_seconds() / 3600)
    freshness = max(0.0, 1.0 - age_hours / (72.0 * 1.0))
    total_votes = confirmations + rejections
    community = 0.5 if total_votes == 0 else max(0.0, min(1.0, 0.5 + (confirmations - rejections) / (2 * max(total_votes, 1))))
    score = 0.65 * freshness + 0.35 * community
    return round(score * 100, 1), round((community * 2 - 1) * 100, 1)
