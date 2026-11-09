"""Panier de la semaine : import des prix relevés, produits équivalents, comparaison de liste."""
from datetime import date

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import OnlineOffer, PriceObservation, Product, ProductGroup, ProductGroupMember
from app.services import catalog
from tests.conftest import HOME

THON_INTER = "3250391111114"
THON_CARREF = "3560071111113"


def payload(**kw):
    return {
        "date": date.today().isoformat(),
        "zone": {"latitude": HOME[0], "longitude": HOME[1], "radius_km": 10},
        "stores": {"intermarche": {"city": "Maisons-Laffitte"}},
        "lines": [{"line": "Thon, 3 × 140 g", "offers": [
            {"retailer": "intermarche", "ean": THON_INTER, "name": "Thon entier au naturel", "brand": "Pâturages",
             "quantity": "3 x 140 g", "price": 6.27, "url": "https://www.intermarche.com/produit/x"},
            {"retailer": "carrefour", "ean": THON_CARREF, "name": "Thon au naturel", "brand": "Carrefour",
             "quantity": "3 x 140 g", "price": "5,37", "regular_price": 5.99},
            {"retailer": "auchan", "name": "Thon sans code", "price": 6.63},
        ]}],
        **kw,
    }


@pytest.fixture(autouse=True)
def offline_catalog(monkeypatch):
    monkeypatch.setattr(catalog, "lookup_ean", lambda ean: None)


@pytest.fixture
def visible(monkeypatch):
    monkeypatch.setattr(settings, "enable_online_prices", True)
    monkeypatch.setattr(settings, "online_retailers", "")


def test_import_creates_prices_products_and_group(client, db, factory, visible):
    inter = factory.store("Intermarché Super")
    factory.store("Intermarché Contact", city="Sartrouville", lat=HOME[0] + 0.01)
    market = factory.store("Carrefour Market", lat=HOME[0] + 0.005)
    factory.store("Carrefour City", lat=HOME[0] + 0.006)

    stats = client.post("/imports/basket", json=payload()).json()
    assert stats["offers"] == 2 and stats["new_products"] == 2 and stats["prices_in_stores"] == 2
    assert stats["skipped"] == ["Thon, 3 × 140 g · auchan : code-barres absent ou invalide"]

    obs = {o.store_id: o for o in db.scalars(select(PriceObservation))}
    assert set(obs) == {inter.id, market.id}  # magasin choisi pour Intermarché, pas les formats proximité Carrefour
    assert obs[market.id].is_promotion and str(obs[market.id].regular_price) == "5.99"
    created = db.scalar(select(Product).where(Product.ean == THON_INTER))
    assert (created.name, created.brand, created.source) == ("Thon entier au naturel", "Pâturages", "basket")
    assert db.scalar(select(ProductGroup)).name == "Thon, 3 × 140 g"
    assert len(db.scalars(select(ProductGroupMember)).all()) == 2

    # Renvoyer le même panier ne crée pas de doublon
    again = client.post("/imports/basket", json=payload()).json()
    assert again["prices_in_stores"] == 0 and len(db.scalars(select(OnlineOffer)).all()) == 2


def test_product_page_shows_equivalents(client, factory, visible):
    factory.store("Intermarché Super")
    factory.store("Carrefour Market", lat=HOME[0] + 0.005)
    client.post("/imports/basket", json=payload())
    body = client.get(f"/products/{THON_INTER}/comparison", params={"latitude": HOME[0], "longitude": HOME[1]}).json()
    assert [r["chain"] for r in body["results"]] == ["Intermarché Super"]
    eq = body["equivalents"]
    assert len(eq) == 1 and eq[0]["product"]["ean"] == THON_CARREF and eq[0]["price"] == 5.37
    assert eq[0]["group"] == "Thon, 3 × 140 g" and eq[0]["source_label"] == "Prix carrefour.fr"


def test_list_comparison_uses_equivalents(client, factory, visible):
    factory.store("Intermarché Super")
    market = factory.store("Carrefour Market", lat=HOME[0] + 0.005)
    client.post("/imports/basket", json=payload())
    client.post("/users/selim-device-1/list", json={"ean": THON_INTER, "quantity": 2})
    body = client.get("/users/selim-device-1/list/comparison",
                      params={"latitude": HOME[0], "longitude": HOME[1]}).json()
    by_chain = {s["chain"]: s for s in body["stores"]}
    assert by_chain["Carrefour Market"]["known_total"] == 10.74  # 2 × 5,37 : thon Carrefour à la place
    assert by_chain["Carrefour Market"]["substituted"][0]["with"]["ean"] == THON_CARREF
    assert by_chain["Intermarché Super"]["known_total"] == 12.54 and not by_chain["Intermarché Super"]["substituted"]
    assert body["stores"][0]["store_id"] == market.id


def test_imported_prices_stay_private_when_disabled(client, factory, monkeypatch):
    monkeypatch.setattr(settings, "enable_online_prices", False)
    factory.store("Intermarché Super")
    stats = client.post("/imports/basket", json=payload()).json()
    assert stats["visible_in_app"] is False and stats["prices_in_stores"] == 1
    body = client.get(f"/products/{THON_INTER}/comparison", params={"latitude": HOME[0], "longitude": HOME[1]}).json()
    assert body["results"] == []


def test_invalid_payloads(client):
    assert client.post("/imports/basket", json={"lines": []}).json()["detail"]["code"] == "invalid_basket"
    bad_zone = {"lines": [{"line": "x", "offers": []}]}
    assert client.post("/imports/basket", json=bad_zone).status_code == 422


def test_watchlist_and_page(client, factory):
    factory.product()
    client.post("/users/selim-device-1/list", json={"ean": "3017620422003"})
    assert client.get("/imports/watchlist").json() == [
        {"ean": "3017620422003", "name": "Nutella", "brand": "Ferrero", "quantity": "400 g", "line": None}]
    page = client.get("/imports")
    assert page.status_code == 200 and 'id="payload"' in page.text and 'id="import"' in page.text
