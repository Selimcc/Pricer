from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services.ean import normalize_ean
from app.services.quantity import from_off, parse_quantity, unit_price
from app.services.scoring import confidence_for


def test_ean13_valid_and_invalid():
    assert normalize_ean("3017620422003") == "3017620422003"
    assert normalize_ean(" 3017620422003 ") == "3017620422003"
    assert normalize_ean("3017620422004") is None  # mauvaise clé de contrôle
    assert normalize_ean("301762042200") is None
    assert normalize_ean("abc") is None


def test_upc_a_becomes_ean13():
    assert normalize_ean("036000291452") == "0036000291452"


def test_ean8_and_upc_e():
    assert normalize_ean("96385074") == "96385074"
    # UPC-E 04252614 -> UPC-A 042100005264
    assert normalize_ean("04252614") == "0042100005264"


def test_parse_quantity():
    assert parse_quantity("400 g") == (Decimal(400), "g")
    assert parse_quantity("1,5 L") == (Decimal(1500), "ml")
    assert parse_quantity("6 x 33 cl") == (Decimal(1980), "ml")
    assert parse_quantity("1kg") == (Decimal(1000), "g")
    assert parse_quantity("lot de 3") == (None, None)
    assert from_off(400, "g", None) == (Decimal(400), "g")
    assert from_off(None, None, "75 cl") == (Decimal(750), "ml")


def test_unit_price():
    assert unit_price(4.19, Decimal(400), "g") == (10.48, "€/kg")
    assert unit_price(2.10, Decimal(1500), "ml") == (1.4, "€/L")
    assert unit_price(2.10, None, None) == (None, None)


def test_confidence_freshness_and_community():
    now = datetime.now(timezone.utc)
    fresh = confidence_for(now, 0, 0, now=now)
    week = confidence_for(now - timedelta(days=7), 0, 0, now=now)
    month = confidence_for(now - timedelta(days=30), 0, 0, now=now)
    assert fresh["confidence"] > week["confidence"] > month["confidence"]
    assert week["freshness"] == 50.0  # demi-vie 7 jours

    confirmed = confidence_for(now, 4, 0, now=now)
    contested = confidence_for(now, 0, 4, now=now)
    assert confirmed["confidence"] > fresh["confidence"] > contested["confidence"]

    proven = confidence_for(now, 0, 0, has_proof=True, gps_verified=True, now=now)
    assert proven["confidence"] > fresh["confidence"]
    assert proven["confidence_level"] == "high"

    flagged = confidence_for(now, 0, 0, flagged=True, now=now)
    assert flagged["confidence"] == round(fresh["confidence"] / 2, 1)
