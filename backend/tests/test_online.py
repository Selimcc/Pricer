"""Prix des sites des enseignes : politesse (robots.txt, blocage), lecture des pages, rattachement aux magasins.

Aucun accès réseau : les sites sont simulés avec httpx.MockTransport.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.jobs import purge
from app.models import OnlineCatalogUrl, OnlineOffer, OnlineRetailerState, PriceObservation
from app.services import online
from app.services.online import http, matching, parse
from app.services.online.retailers import RETAILERS
from app.services.online.sitemaps import index_retailer
from tests.conftest import HOME

CRISTALINE = "3274080005003"

PRODUCT_PAGE = f"""<html><head>
<script type="application/ld+json">{{
  "@context": "https://schema.org", "@type": "Product", "name": "Eau de source Cristaline 1,5L",
  "brand": {{"@type": "Brand", "name": "Cristaline"}}, "gtin13": "{CRISTALINE}",
  "offers": {{"@type": "Offer", "price": "0.39", "priceCurrency": "EUR",
             "availability": "https://schema.org/InStock"}}
}}</script></head><body>{"x" * 20000}</body></html>"""

ROBOTS = """User-agent: *
Disallow: /recherche
Disallow: /*?code
Allow: /recherche/ok$
Sitemap: https://www.example.fr/sitemap.xml
"""


def site(routes: dict[str, tuple[int, str]]):
    """Faux site : chemin (avec requête) -> (statut, contenu). Compte les requêtes."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.raw_path.decode()
        calls.append(key)
        status, body = routes.get(key, (404, "introuvable"))
        return httpx.Response(status, text=body)

    return http.PoliteClient(min_delay_s=0, transport=httpx.MockTransport(handler)), calls


@pytest.fixture
def online_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_online_prices", True)
    monkeypatch.setattr(settings, "online_retailers", "leclerc,carrefour,auchan")
    yield


# ---------------------------------------------------------------- robots.txt et blocages

def test_robots_rules_wildcards_and_longest_match():
    rules = http.parse_robots(ROBOTS)
    assert not rules.allows("/recherche?q=1")
    assert rules.allows("/recherche/ok")
    assert not rules.allows("/recherche/ok/plus")
    assert not rules.allows("/produit?code=12")
    assert rules.allows("/fp/3274080005003")
    assert http.sitemaps_from_robots(ROBOTS) == ["https://www.example.fr/sitemap.xml"]


def test_robots_specific_group_wins():
    rules = http.parse_robots("User-agent: *\nDisallow: /\n\nUser-agent: Pricer\nAllow: /\n", "Pricer/0.6")
    assert rules.allows("/fp/1")


def test_block_detection():
    assert http.looks_blocked(403, "")
    assert http.looks_blocked(200, '<script src="https://ct.captcha-delivery.com/c.js"></script>')
    assert not http.looks_blocked(200, PRODUCT_PAGE)


def test_client_refuses_disallowed_paths():
    client, calls = site({"/robots.txt": (200, ROBOTS)})
    with pytest.raises(http.NotAllowed):
        client.get("https://www.example.fr/recherche?q=x")
    assert calls == ["/robots.txt"]


def test_client_daily_cap():
    client, _ = site({"/robots.txt": (200, ""), "/a": (200, PRODUCT_PAGE)})
    client.daily_cap = 2
    client.get("https://www.example.fr/a")
    with pytest.raises(http.SiteBlocked):
        client.get("https://www.example.fr/a")


# ---------------------------------------------------------------- lecture des pages

def test_parse_jsonld_product():
    offer = parse.find_offer(PRODUCT_PAGE, CRISTALINE)
    assert offer.price == Decimal("0.39") and offer.matched_by == "gtin" and not offer.is_promotion


def test_parse_graph_promotion_and_wrong_product():
    page = """<script type="application/ld+json">{"@graph": [{"@type": "WebPage"}, {"@type": ["Product"],
      "gtin": "03274080005003", "offers": [{"@type": "Offer", "price": "0,35", "priceCurrency": "EUR",
      "priceSpecification": [{"@type": "UnitPriceSpecification", "priceType": "https://schema.org/StrikethroughPrice",
      "price": 0.45}]}]}]}</script>"""
    offer = parse.find_offer(page, CRISTALINE)
    assert offer.price == Decimal("0.35") and offer.regular_price == Decimal("0.45") and offer.is_promotion
    # Une page d'un autre produit ne donne jamais de prix
    assert parse.find_offer(page, "3017620422003") is None


def test_parse_meta_fallback_requires_ean_in_page():
    page = '<meta property="product:price:amount" content="1.99"><p>EAN 3017620422003</p>'
    assert parse.find_offer(page, "3017620422003").price == Decimal("1.99")
    assert parse.find_offer(page, CRISTALINE) is None


# ---------------------------------------------------------------- recherche dans les sitemaps

def test_slug_and_matching(db, factory):
    p = factory.product(ean=CRISTALINE, name="Eau de source", brand="Cristaline", quantity="1,5 L",
                        quantity_value=1500, quantity_unit="ml")
    assert matching.slug_of("https://courses.monoprix.fr/products/cristaline-eau-de-source-1-5l/MPX_3908291") == \
        "products cristaline eau de source 1 5l"
    db.add_all([
        OnlineCatalogUrl(retailer="auchan", url="https://a.fr/cristaline-eau-de-source-1-5l/pr-C1",
                         slug="cristaline eau de source 1 5l"),
        OnlineCatalogUrl(retailer="auchan", url="https://a.fr/cristaline-eau-de-source-6x1-5l/pr-C2",
                         slug="cristaline eau de source 6x1 5l pack"),
        OnlineCatalogUrl(retailer="auchan", url="https://a.fr/evian-eau-1-5l/pr-C3", slug="evian eau minerale 1 5l"),
    ])
    db.commit()
    assert matching.best_urls(db, "auchan", p)[0] == "https://a.fr/cristaline-eau-de-source-1-5l/pr-C1"
    assert "https://a.fr/evian-eau-1-5l/pr-C3" not in matching.best_urls(db, "auchan", p, limit=5)


def test_sitemap_indexing(db):
    index = """<sitemapindex><sitemap><loc>https://www.auchan.fr/sitemaps/sitemap-products1.xml</loc></sitemap>
               <sitemap><loc>https://www.auchan.fr/sitemaps/sitemap-stores.xml</loc></sitemap></sitemapindex>"""
    products = """<urlset><url><loc>https://www.auchan.fr/cristaline-eau-de-source-1-5l/pr-C123</loc></url>
                  <url><loc>https://www.auchan.fr/nutella-400g/pr-C456</loc></url></urlset>"""
    client, calls = site({"/robots.txt": (200, ""), "/sitemaps/sitemap-products.xml": (200, index),
                          "/sitemaps/sitemap-products1.xml": (200, products)})
    assert index_retailer(db, client, RETAILERS["auchan"]) == 2
    assert "/sitemaps/sitemap-stores.xml" not in calls  # seuls les sitemaps produits sont lus
    assert db.get(OnlineRetailerState, "auchan").sitemap_indexed_at is not None


# ---------------------------------------------------------------- recherche d'un prix

def test_lookup_direct_retailer(db, factory, online_on):
    p = factory.product(ean=CRISTALINE, name="Eau de source", brand="Cristaline")
    client, calls = site({"/robots.txt": (200, ""), f"/fp/{CRISTALINE}": (200, PRODUCT_PAGE)})
    offer = online.lookup(db, RETAILERS["leclerc"], p, client)
    assert offer.price == Decimal("0.39") and offer.url.endswith(f"/fp/{CRISTALINE}")
    assert calls == ["/robots.txt", f"/fp/{CRISTALINE}"]
    assert online.is_fresh(offer)


def test_lookup_search_retailer_follows_product_link(db, factory, online_on):
    p = factory.product(ean=CRISTALINE, name="Eau de source", brand="Cristaline")
    search = f'<a href="/p/eau-de-source-cristaline-{CRISTALINE}">Cristaline</a>'
    client, calls = site({"/robots.txt": (200, ""), f"/s?q={CRISTALINE}": (200, search),
                          f"/p/eau-de-source-cristaline-{CRISTALINE}": (200, PRODUCT_PAGE)})
    assert online.lookup(db, RETAILERS["carrefour"], p, client).price == Decimal("0.39")


def test_lookup_not_found_is_cached(db, factory, online_on):
    p = factory.product(ean=CRISTALINE, name="Eau de source", brand="Cristaline")
    client, _ = site({"/robots.txt": (200, "")})
    assert online.lookup(db, RETAILERS["leclerc"], p, client) is None
    row = db.scalar(select(OnlineOffer))
    assert row.found is False and online.is_fresh(row)


def test_blocked_site_is_left_alone(db, factory, online_on):
    p = factory.product(ean=CRISTALINE, name="Eau de source", brand="Cristaline")
    client, calls = site({"/robots.txt": (200, ""), f"/fp/{CRISTALINE}": (403, "Forbidden")})
    assert online.lookup(db, RETAILERS["leclerc"], p, client) is None
    assert online.is_blocked(db, "leclerc")
    online.lookup(db, RETAILERS["leclerc"], p, client)
    assert calls.count(f"/fp/{CRISTALINE}") == 1  # aucune nouvelle tentative pendant la pause
    assert db.scalar(select(OnlineOffer)) is None  # pas de faux « absent » en cache


# ---------------------------------------------------------------- rattachement et visibilité

def _offer(db, product, retailer="carrefour", price="0.39", **kw):
    db.add(OnlineOffer(retailer=retailer, product_id=product.id, found=True, price=Decimal(price),
                       is_promotion=False, url="https://x", checked_at=kw.get("at", datetime.now(timezone.utc))))
    db.commit()


def test_attach_only_to_matching_chains(db, factory, online_on):
    p = factory.product()
    market = factory.store("Carrefour Market")
    city = factory.store("Carrefour City")
    franprix = factory.store("Franprix")
    _offer(db, p)
    stores = [(market, 0.2), (city, 0.3), (franprix, 0.4)]
    assert online.attach(db, [p], stores) == 1
    obs = db.scalar(select(PriceObservation))
    assert obs.store_id == market.id and obs.source == "online" and obs.user_id == "online:carrefour"
    # Même prix le même jour : pas de doublon
    assert online.attach(db, [p], stores) == 0


def test_online_prices_hidden_when_disabled(client, db, factory, monkeypatch):
    p = factory.product()
    store = factory.store("Carrefour Market")
    factory.price(p, store, 4.10, source="online", user_id="online:carrefour")
    params = {"latitude": HOME[0], "longitude": HOME[1]}

    monkeypatch.setattr(settings, "enable_online_prices", False)
    body = client.get(f"/products/{p.ean}/comparison", params=params).json()
    assert body["results"] == []
    assert client.get(f"/products/{p.ean}/history").json()["points"] == []
    assert client.get("/stores/nearby", params=params).json()[0]["price_count"] == 0

    monkeypatch.setattr(settings, "enable_online_prices", True)
    monkeypatch.setattr(online, "refresh", lambda *a, **k: None)
    row = client.get(f"/products/{p.ean}/comparison", params=params).json()["results"][0]
    assert row["price"] == 4.10 and row["source_label"] == "Prix carrefour.fr"


def test_comparison_fetches_and_shows_online_price(client, db, factory, online_on, monkeypatch):
    factory.product(ean=CRISTALINE, name="Eau de source", brand="Cristaline")
    factory.store("E.Leclerc", lat=HOME[0] + 0.01)
    mock, _ = site({"/robots.txt": (200, ""), f"/fp/{CRISTALINE}": (200, PRODUCT_PAGE)})
    monkeypatch.setattr(settings, "online_retailers", "leclerc")
    monkeypatch.setattr(http, "_client", mock)
    body = client.get(f"/products/{CRISTALINE}/comparison", params={"latitude": HOME[0], "longitude": HOME[1]}).json()
    assert [r["price"] for r in body["results"]] == [0.39]
    assert body["results"][0]["chain"] == "E.Leclerc"


def test_purge_online(db, factory):
    p = factory.product()
    store = factory.store("Carrefour Market")
    factory.price(p, store, 4.10, source="online", user_id="online:carrefour")
    factory.price(p, store, 4.20)
    _offer(db, p, at=datetime.now(timezone.utc) - timedelta(days=1))
    assert purge.purge_online(db) == 1
    assert [o.source for o in db.scalars(select(PriceObservation))] == ["community"]
    assert db.scalar(select(OnlineOffer)) is None


def test_cache_row_is_updated_in_place(db, factory):
    p = factory.product()
    online._save(db, "leclerc", p.id, found=False)
    online._save(db, "leclerc", p.id, found=True, price=Decimal("4.10"), url="https://x")
    rows = db.scalars(select(OnlineOffer)).all()
    assert len(rows) == 1 and rows[0].found and rows[0].price == Decimal("4.10")


def test_sitemap_retailer_waits_for_its_index(db, factory, online_on):
    p = factory.product(ean=CRISTALINE, name="Eau de source", brand="Cristaline")
    client, calls = site({"/robots.txt": (200, "")})
    assert online.lookup(db, RETAILERS["auchan"], p, client) is None
    assert calls == [] and db.scalar(select(OnlineOffer)) is None


# Extrait réduit d'une vraie fiche auchan.fr (7 octobre 2026) : microdonnées, pas de JSON-LD
AUCHAN_PAGE = """<div class="offer-selector__price-wrapper product-price__container" itemprop="offers" itemscope="itemscope"
 itemtype="http://schema.org/Offer"><del class="product-price product-price--small product-price--old text-dark-color normal"
 aria-label="Ancien prix : 30,00&#x20AC;">30,00&#x20AC;</del><div class="product-price product-price--large bolder red-txt">
 16,85&#x20AC;</div><meta itemprop="price" content="16.85"><meta itemprop="priceCurrency" content="EUR"></div>
<article itemscope="itemscope" itemtype="http://schema.org/Product" class="product-thumbnail"><div itemprop="offers">
 <meta itemprop="price" content="4.99"></div></article>
<span class="product-description__feature-label">R&#xE9;f / EAN :</span><div class="product-description__feature-values">
 C774424 / 4007176128428 </div>"""


def test_auchan_microdata_reader():
    offer = parse.auchan_offer(AUCHAN_PAGE, "4007176128428")
    assert offer.price == Decimal("16.85") and offer.regular_price == Decimal("30.00") and offer.is_promotion
    assert parse.auchan_offer(AUCHAN_PAGE, CRISTALINE) is None  # autre produit affiché : pas de prix
    assert parse.declared_eans(AUCHAN_PAGE) == {"4007176128428"}


def test_lookup_uses_site_reader_first(db, factory, online_on):
    p = factory.product(ean="4007176128428", name="Figurine Disney Cristaline", brand="Bullyland")
    url = "https://www.auchan.fr/bullyland-figurine-disney-cristaline/pr-C774424"
    db.add(OnlineCatalogUrl(retailer="auchan", url=url, slug=matching.slug_of(url)))
    db.commit()
    client, _ = site({"/robots.txt": (200, ""), "/bullyland-figurine-disney-cristaline/pr-C774424": (200, AUCHAN_PAGE)})
    trace = []
    offer = online.lookup(db, RETAILERS["auchan"], p, client, trace=trace)
    assert offer.price == Decimal("16.85") and offer.is_promotion and offer.regular_price == Decimal("30.00")
    assert [t["étape"] for t in trace] == ["candidats sitemap", "pages à essayer", "page"]
