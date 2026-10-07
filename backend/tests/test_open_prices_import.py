"""Import complet d'Open Prices (export quotidien) et tâches de nuit."""
import gzip
import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.jobs import open_prices_import as opi
from app.jobs import worker
from app.models import PriceObservation, Product, Store
from app.services import catalog
from tests.test_external_sources import OPEN_PRICES_ITEM

TODAY = date.today().isoformat()
IDF = opi.parse_bbox("48.12,1.44,49.24,3.56")

# Format « à plat » de l'export (mêmes colonnes que le jeu de données publié)
FLAT_ITEM = {
    "id": 900001, "type": "PRODUCT", "product_code": "3274080005003", "product_name": "Cristaline 1,5 L",
    "price": 0.39, "price_is_discounted": False, "currency": "EUR", "date": TODAY, "owner": "bob",
    "location_type": "OSM", "location_osm_id": 123456, "location_osm_type": "NODE",
    "location_osm_lat": 48.8925, "location_osm_lon": 2.2069,
    "location_osm_display_name": "Carrefour Market, 12 Rue X, Nanterre, France",
    "location_osm_address_city": "Nanterre", "location_osm_tag_value": "supermarket",
    "proof_file_path": "0001/abc.webp",
}


def test_import_flat_and_nested_items_in_area(db, factory):
    factory.product()  # Nutella déjà connu
    nancy = {**OPEN_PRICES_ITEM, "date": TODAY}  # hors Île-de-France
    paris = {**OPEN_PRICES_ITEM, "id": 900002, "date": TODAY,
             "location": {**OPEN_PRICES_ITEM["location"], "osm_id": 999, "osm_lat": 48.86, "osm_lon": 2.35}}
    old = {**FLAT_ITEM, "id": 900003, "date": "2020-01-01"}
    stats = opi.import_items(db, [FLAT_ITEM, nancy, paris, old], IDF, date.today() - timedelta(days=365))
    assert stats["in_area"] == 2 and stats["imported"] == 2 and stats["new_products"] == 1

    stub = db.scalar(select(Product).where(Product.ean == "3274080005003"))
    assert stub.name == "Cristaline 1,5 L" and stub.source == opi.STUB_SOURCE
    store = db.scalar(select(Store).where(Store.osm_id == 123456))
    assert store.chain == "Carrefour Market" and store.city == "Nanterre"
    obs = db.scalar(select(PriceObservation).where(PriceObservation.external_id == "900001"))
    assert obs.source == "open_prices" and obs.proof_image_url.endswith("0001/abc.webp")

    # Relancer l'import ne crée pas de doublon
    assert opi.import_items(db, [FLAT_ITEM, paris], IDF, date(2000, 1, 1))["imported"] == 0


def test_import_reads_gzip_export(db, tmp_path):
    path = tmp_path / "prices.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps(FLAT_ITEM) + "\n\n{pas du json\n")
    assert [i["id"] for i in opi.read_jsonl(path)] == [900001]


def test_imported_product_is_completed_on_first_scan(client, db, monkeypatch):
    opi.import_items(db, [FLAT_ITEM], IDF, date(2000, 1, 1))
    monkeypatch.setattr(catalog, "lookup_ean", lambda ean: {
        "name": catalog.UNNAMED, "brand": "Cristaline", "quantity": "1,5 L", "image_url": "https://img/x.jpg",
        "quantity_value": 1500, "quantity_unit": "ml", "nutriscore_grade": None, "source": "off"})
    body = client.get("/products/3274080005003").json()
    assert body["name"] == "Cristaline 1,5 L"  # le nom importé est gardé plutôt que « Produit sans nom »
    assert body["brand"] == "Cristaline" and body["image_url"] == "https://img/x.jpg" and body["source"] == "off"


def test_worker_schedule(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(worker.settings, "worker_hour_utc", 2)
    monday_night = datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc)
    assert worker.is_due("x", "daily", {}, monday_night)  # jamais lancée
    assert not worker.is_due("x", "daily", {"x": "2026-10-05"}, monday_night)
    assert worker.is_due("x", "daily", {"x": "2026-10-04"}, monday_night)
    assert not worker.is_due("x", "daily", {"x": "2026-10-04"}, monday_night.replace(hour=1))
    assert worker.is_due("w", "weekly", {"w": "2026-09-28"}, monday_night)
    assert not worker.is_due("w", "weekly", {"w": "2026-09-28"}, monday_night + timedelta(days=1))

    ran = []
    monkeypatch.setattr(worker, "TASKS", [("a", lambda: ran.append("a"), lambda: True, "daily"),
                                          ("b", lambda: ran.append("b"), lambda: False, "daily")])
    assert worker.run_due(monday_night) == ["a"] and worker.run_due(monday_night) == []
