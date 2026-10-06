"""Quantités produit et prix au kilo / litre / unité."""
import re
from decimal import ROUND_HALF_UP, Decimal

_UNITS = {
    "g": ("g", Decimal(1)),
    "gr": ("g", Decimal(1)),
    "kg": ("g", Decimal(1000)),
    "mg": ("g", Decimal("0.001")),
    "ml": ("ml", Decimal(1)),
    "cl": ("ml", Decimal(10)),
    "dl": ("ml", Decimal(100)),
    "l": ("ml", Decimal(1000)),
    "litre": ("ml", Decimal(1000)),
    "litres": ("ml", Decimal(1000)),
}

_MULTI = re.compile(r"(\d+)\s*[x×*]\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)\b")
_SIMPLE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)\b")


def _to_decimal(s: str) -> Decimal:
    return Decimal(s.replace(",", "."))


def parse_quantity(text: str | None) -> tuple[Decimal | None, str | None]:
    """'400 g' -> (400, 'g') ; '6 x 33 cl' -> (1980, 'ml') ; '1,5 L' -> (1500, 'ml')."""
    if not text:
        return None, None
    t = text.lower()
    m = _MULTI.search(t)
    if m and m.group(3) in _UNITS:
        unit, factor = _UNITS[m.group(3)]
        return int(m.group(1)) * _to_decimal(m.group(2)) * factor, unit
    for m in _SIMPLE.finditer(t):
        if m.group(2) in _UNITS:
            unit, factor = _UNITS[m.group(2)]
            return _to_decimal(m.group(1)) * factor, unit
    return None, None


def from_off(product_quantity, product_quantity_unit, quantity_text) -> tuple[Decimal | None, str | None]:
    """Utilise les champs structurés d'Open Food Facts quand ils existent."""
    try:
        if product_quantity and product_quantity_unit:
            unit = str(product_quantity_unit).lower()
            if unit in _UNITS:
                base_unit, factor = _UNITS[unit]
                value = Decimal(str(product_quantity)) * factor
                if value > 0:
                    return value, base_unit
    except Exception:
        pass
    return parse_quantity(quantity_text)


def unit_price(price: float, quantity_value, quantity_unit) -> tuple[float | None, str | None]:
    """Prix ramené au kilo (g) ou au litre (ml), arrondi au centime supérieur à partir de 0,5."""
    if not quantity_value or not quantity_unit:
        return None, None
    value = Decimal(str(quantity_value))
    if value <= 0:
        return None, None
    amount = Decimal(str(price))
    if quantity_unit in ("g", "ml"):
        per = amount * 1000 / value
        label = "€/kg" if quantity_unit == "g" else "€/L"
    elif quantity_unit == "unit":
        per, label = amount / value, "€/unité"
    else:
        return None, None
    return float(per.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)), label
