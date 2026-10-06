"""Open Prices et OpenStreetMap, avec des réponses enregistrées (pas de réseau)."""
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.models import PriceObservation, Store
from app.services import osm
from app.services.providers import open_prices
from tests.conftest import HOME

# Extrait réel de GET /api/v1/prices?product_code=3017620422003 (octobre 2026), raccourci
OPEN_PRICES_ITEM = {
    "id": 341942,
    "type": "PRODUCT",
    "product_code": "3017620422003",
    "price": 4.45,
    "price_is_discounted": False,
    "price_without_discount": None,
    "discount_type": None,
    "price_per": None,
    "currency": "EUR",
    "location_osm_id": 3423864836,
    "location_osm_type": "NODE",
    "date": "2026-10-06",
    "owner": "poslovitch",
    "duplicate_of": None,
    "location": {
        "type": "OSM", "osm_id": 3423864836, "osm_type": "NODE",
        "osm_name": "Carrefour Express Nancy Leopold", "osm_brand": "Carrefour Express",
        "osm_tag_key": "shop", "osm_tag_value": "convenience",
        "osm_address_postcode": "54100", "osm_address_city": "Nancy",
        "osm_lat": 48.6945513, "osm_lon": 6.1775365,
    },
    "proof": {"id": 138142, "file_path": "0319/eO7zuPUmSS.webp", "type": "PRICE_TAG"},
}

DISCOUNTED_ITEM = {
    **OPEN_PRICES_ITEM, "id": 341943, "price": 3.99, "price_is_discounted": True,
    "price_without_discount": 4.79, "discount_type": "LOYALTY_PROGRAM", "proof": None,
}

OVERPASS_RESPONSE = {
    "elements": [
        {"type": "node", "id": 101, "lat": 48.9481, "lon": 2.1462,
         "tags": {"shop": "supermarket", "name": "Carrefour Market", "brand": "Carrefour Market",
                  "addr:housenumber": "12", "addr:street": "Rue de Paris", "addr:city": "Maisons-Laffitte",
                  "addr:postcode": "78600"}},
        {"type": "way", "id": 202, "center": {"lat": 48.9400, "lon": 2.1500},
         "tags": {"shop": "supermarket", "name": "Lidl"}},
        {"type": "node", "id": 303, "lat": 48.95, "lon": 2.15, "tags": {"shop": "convenience"}},  # sans nom
    ]
}


def test_open_prices_sync(factory, db, monkeypatch):
    monkeypatch.setattr(settings, "enable_open_prices", True)
    calls = []

    def fake_fetch(self, ean):
        calls.append(ean)
        return [OPEN_PRICES_ITEM, DISCOUNTED_ITEM, {**OPEN_PRICES_ITEM, "id": 9, "currency": "USD"}]

    monkeypatch.setattr(open_prices.OpenPricesProvider, "fetch", fake_fetch)
    product = factory.product()
    provider = open_prices.OpenPricesProvider()

    assert provider.sync_product(db, product) == 2
    store = db.query(Store).one()
    assert (store.osm_type, store.osm_id, store.chain) == ("node", 3423864836, "Carrefour Express")
    obs = {o.external_id: o for o in db.query(PriceObservation).all()}
    assert obs["341942"].proof_image_url == "https://prices.openfoodfacts.org/img/0319/eO7zuPUmSS.webp"
    assert obs["341943"].promotion_type == "loyalty" and float(obs["341943"].regular_price) == 4.79

    # Synchronisé récemment : pas de nouvel appel
    assert provider.sync_product(db, product) == 0 and len(calls) == 1
    # Plus tard : nouvel appel, mais pas de doublon
    product.prices_synced_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    assert provider.sync_product(db, product) == 0 and len(calls) == 2
    assert db.query(PriceObservation).count() == 2


def test_parse_overpass():
    stores = osm.parse_overpass(OVERPASS_RESPONSE)
    assert [s["name"] for s in stores] == ["Carrefour Market", "Lidl"]
    assert stores[0]["address"] == "12 Rue de Paris" and stores[1]["latitude"] == 48.94


def test_area_import_is_cached(client, db, monkeypatch):
    monkeypatch.setattr(settings, "enable_osm_import", True)
    calls = []

    def fake_fetch(lat, lon, radius):
        calls.append(radius)
        return osm.parse_overpass(OVERPASS_RESPONSE)

    monkeypatch.setattr(osm, "fetch_overpass", fake_fetch)
    params = {"latitude": HOME[0], "longitude": HOME[1], "radius_km": 3}
    stores = client.get("/stores/nearby", params=params).json()
    assert {s["name"] for s in stores} == {"Carrefour Market", "Lidl"}
    client.get("/stores/nearby", params={**params, "radius_km": 2})
    assert len(calls) == 1  # zone déjà couverte

    # Un échec réseau ne casse pas la recherche
    monkeypatch.setattr(osm, "fetch_overpass", lambda *a: None)
    r = client.get("/stores/nearby", params={"latitude": 45.76, "longitude": 4.83, "radius_km": 3})
    assert r.status_code == 200 and r.json() == []
