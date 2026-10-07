"""Lecture du prix et du code-barres dans une page produit.

Les sites marchands décrivent leurs produits pour les moteurs de recherche
(schema.org en JSON-LD ou en microdonnées) : nom, marque, GTIN/EAN, prix.
C'est cette description qu'on lit, pas la mise en page (qui change souvent).
"""
import html as html_lib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

LD_JSON_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL
)
GTIN_KEYS = ("gtin13", "gtin", "gtin12", "gtin14", "gtin8", "ean", "ean13")
LIST_PRICE_TYPES = ("listprice", "strikethroughprice", "msrp", "regularprice")


@dataclass
class PageProduct:
    name: str | None = None
    brand: str | None = None
    gtins: set[str] = field(default_factory=set)
    price: Decimal | None = None
    regular_price: Decimal | None = None
    currency: str | None = None
    available: bool | None = None


def to_price(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace("\xa0", "").replace("€", "").replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        price = Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return price if Decimal("0.01") <= price <= Decimal("10000") else None


def same_ean(a: str, b: str) -> bool:
    """EAN-13, UPC-12 et GTIN-14 d'un même produit ne diffèrent que par des zéros de tête."""
    a, b = re.sub(r"\D", "", a or ""), re.sub(r"\D", "", b or "")
    return bool(a) and bool(b) and a.lstrip("0") == b.lstrip("0")


def _types(node: dict) -> list[str]:
    t = node.get("@type")
    return [str(x).lower() for x in (t if isinstance(t, list) else [t]) if x]


def _walk(node, found: list[dict]):
    if isinstance(node, list):
        for item in node:
            _walk(item, found)
    elif isinstance(node, dict):
        if "product" in _types(node) or "productgroup" in _types(node):
            found.append(node)
        for key in ("@graph", "mainEntity", "itemListElement", "item", "hasVariant"):
            if key in node:
                _walk(node[key], found)


def _load_json(raw: str):
    raw = raw.strip()
    if raw.startswith("<!--"):
        raw = raw.removeprefix("<!--").removesuffix("-->")
    raw = raw.replace("//<![CDATA[", "").replace("//]]>", "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:  # retours à la ligne bruts dans des chaînes, fréquent
            return json.loads(re.sub(r"[\x00-\x1f]", " ", raw))
        except json.JSONDecodeError:
            return None


def _offer_prices(offers) -> tuple[Decimal | None, Decimal | None, str | None, bool | None]:
    """(prix, prix barré, devise, disponible) à partir du bloc « offers »."""
    items = offers if isinstance(offers, list) else [offers]
    best = regular = currency = None
    available = None
    for offer in items:
        if not isinstance(offer, dict):
            continue
        price = to_price(offer.get("price")) or to_price(offer.get("lowPrice"))
        specs = offer.get("priceSpecification")
        for spec in specs if isinstance(specs, list) else [specs]:
            if not isinstance(spec, dict):
                continue
            kind = str(spec.get("priceType") or "").lower()
            value = to_price(spec.get("price"))
            if any(t in kind for t in LIST_PRICE_TYPES):
                regular = value or regular
            elif price is None:
                price = value
        if price is not None and (best is None or price < best):
            best = price
            currency = offer.get("priceCurrency") or currency
        availability = str(offer.get("availability") or "").lower()
        if availability:
            available = bool(available) or ("instock" in availability or "limitedavailability" in availability)
    return best, regular, currency, available


def products_from_jsonld(page_html: str) -> list[PageProduct]:
    result = []
    for raw in LD_JSON_RE.findall(page_html):
        data = _load_json(html_lib.unescape(raw) if "&quot;" in raw else raw)
        if data is None:
            continue
        nodes: list[dict] = []
        _walk(data, nodes)
        for node in nodes:
            brand = node.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            elif isinstance(brand, list):
                brand = brand[0].get("name") if brand and isinstance(brand[0], dict) else None
            gtins = {re.sub(r"\D", "", str(node[k])) for k in GTIN_KEYS if node.get(k)}
            for k in ("sku", "productID", "mpn"):
                digits = re.sub(r"\D", "", str(node.get(k) or ""))
                if len(digits) in (8, 12, 13, 14):
                    gtins.add(digits)
            price, regular, currency, available = _offer_prices(node.get("offers"))
            result.append(PageProduct(
                name=node.get("name"), brand=brand if isinstance(brand, str) else None,
                gtins={g for g in gtins if g}, price=price, regular_price=regular,
                currency=currency, available=available,
            ))
    return result


def _meta(page_html: str, *names: str) -> str | None:
    for name in names:
        m = re.search(
            rf"<meta[^>]+(?:property|name|itemprop)=[\"']{re.escape(name)}[\"'][^>]*content=[\"']([^\"']+)",
            page_html, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(
            rf"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]*(?:property|name|itemprop)=[\"']{re.escape(name)}[\"']",
            page_html, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def product_from_meta(page_html: str) -> PageProduct | None:
    """Microdonnées / balises meta (product:price:amount, itemprop=price…)."""
    price = to_price(_meta(page_html, "product:price:amount", "og:price:amount", "price"))
    if price is None:
        m = re.search(r"itemprop=[\"']price[\"'][^>]*content=[\"']([^\"']+)", page_html, re.IGNORECASE)
        price = to_price(m.group(1)) if m else None
    if price is None:
        return None
    gtin = _meta(page_html, "gtin13", "gtin", "product:ean", "product:gtin13")
    return PageProduct(name=_meta(page_html, "og:title"), gtins={gtin} if gtin else set(), price=price)


@dataclass
class Offer:
    price: Decimal
    regular_price: Decimal | None
    is_promotion: bool
    name: str | None
    matched_by: str  # gtin | page


def find_offer(page_html: str, ean: str) -> Offer | None:
    """Prix du produit `ean` dans la page, seulement si on est sûr que c'est le bon produit."""
    candidates = products_from_jsonld(page_html)
    meta = product_from_meta(page_html)
    if meta:
        candidates.append(meta)
    priced = [p for p in candidates if p.price is not None and (p.currency or "EUR").upper() == "EUR"]

    for p in priced:
        if any(same_ean(g, ean) for g in p.gtins):
            return _offer(p, "gtin")
    # Pas de GTIN déclaré : on accepte seulement une page à un seul produit qui cite le code-barres
    if len({p.price for p in priced}) == 1 and not any(p.gtins for p in priced) and ean in page_html:
        return _offer(priced[0], "page")
    return None


def page_gtins(page_html: str) -> set[str]:
    return {g for p in products_from_jsonld(page_html) for g in p.gtins}


def _offer(p: PageProduct, how: str) -> Offer:
    promo = p.regular_price is not None and p.price is not None and p.regular_price > p.price
    return Offer(price=p.price, regular_price=p.regular_price if promo else None, is_promotion=promo,
                 name=p.name, matched_by=how)


# ---------------------------------------------------------------- microdonnées (Auchan…)

EAN_LABEL_RE = re.compile(r"EAN\s*:\s*</span>\s*<[^>]+>([^<]+)<", re.IGNORECASE)
DATA_EAN_RE = re.compile(r"data-(?:flix-)?ean=[\"'](\d{8,14})[\"']", re.IGNORECASE)
ITEMPROP_GTIN_RE = re.compile(r"itemprop=[\"']gtin(?:13|8|12|14)?[\"'][^>]*content=[\"'](\d{8,14})", re.IGNORECASE)


def declared_eans(page_html: str) -> set[str]:
    """Codes-barres affichés pour le produit principal (« Réf / EAN : … », data-ean, itemprop gtin)."""
    found = set(DATA_EAN_RE.findall(page_html)) | set(ITEMPROP_GTIN_RE.findall(page_html))
    for value in EAN_LABEL_RE.findall(page_html):
        found |= set(re.findall(r"\b\d{8,14}\b", value))
    return found


def microdata_offer(page_html: str, ean: str, marker: str) -> Offer | None:
    """Prix du bloc d'offre principal (repéré par `marker`), si l'EAN affiché est le bon."""
    if not any(same_ean(e, ean) for e in declared_eans(page_html)):
        return None
    i = page_html.find(marker)
    if i < 0:
        return None
    block = page_html[i:i + 5000]
    m = re.search(r"itemprop=[\"']price[\"'][^>]*content=[\"']([^\"']+)", block)
    price = to_price(m.group(1)) if m else None
    if price is None:
        return None
    old = re.search(r"product-price--old[^>]*>\s*([\d\s.,]+)", block)
    regular = to_price(old.group(1)) if old else None
    promo = regular is not None and regular > price
    return Offer(price=price, regular_price=regular if promo else None, is_promotion=promo, name=None,
                 matched_by="gtin")


def auchan_offer(page_html: str, ean: str) -> Offer | None:
    return microdata_offer(page_html, ean, "offer-selector__price-wrapper")
