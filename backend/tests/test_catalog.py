"""Catalogue multi-sources et catalogue maison."""
from app.core.config import settings
from app.services import catalog

GEL_DOUCHE = {
    "product_name": "Gel douche amande", "brands": "Le Petit Marseillais", "quantity": "250 ml",
    "product_quantity": "250", "product_quantity_unit": "ml", "image_front_url": None,
}
LESSIVE = {"product_name": "Lessive liquide", "brands": "Skip", "quantity": "1,5 L", "image_front_url": "https://img/x.jpg"}


def fake_sources(answers):
    def fetch(source, domain, ean):
        data = answers.get(source)
        return catalog.parse_product(data, source) if data else None
    return fetch


def test_beauty_product_found_outside_food_database(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openfoodfacts", True)
    monkeypatch.setattr(catalog, "fetch_from", fake_sources({"obf": GEL_DOUCHE}))
    r = client.get("/products/3600551054780")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Gel douche amande" and body["source"] == "obf"
    assert body["family"] == "Hygiène et beauté" and body["needs_photo"] is True
    assert body["quantity_unit"] == "ml" and body["nutriscore_grade"] is None


def test_most_complete_record_wins(monkeypatch):
    monkeypatch.setattr(settings, "enable_openfoodfacts", True)
    monkeypatch.setattr(catalog, "fetch_from", fake_sources({"off": {"product_name": ""}, "opf": LESSIVE}))
    found = catalog.lookup_ean("3600551054780")
    assert found["source"] == "opf" and found["name"] == "Lessive liquide"


def test_unknown_everywhere(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openfoodfacts", True)
    monkeypatch.setattr(catalog, "fetch_from", fake_sources({}))
    assert client.get("/products/3600551054780").status_code == 404


def test_community_catalog_photo(client, factory):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
    r = client.post("/products", json={"ean": "3254381025887", "name": "Éponges x3", "user_id": "alice"})
    assert r.status_code == 201 and r.json()["family"] == "Ajouté par la communauté"

    r = client.post("/products/3254381025887/image", data={"user_id": "bob"}, files={"file": ("p.png", png, "image/png")})
    assert r.status_code == 200 and r.json()["image_url"].startswith("/uploads/")
    assert r.json()["needs_photo"] is False
    # Une photo existante n'est pas remplacée
    r = client.post("/products/3254381025887/image", data={"user_id": "eve"}, files={"file": ("p.png", png, "image/png")})
    assert r.status_code == 409

    alice = client.get("/users/alice/contributions").json()
    bob = client.get("/users/bob/contributions").json()
    assert alice["products_added"] == 1 and alice["score"] == 2
    assert bob["photos_added"] == 1 and bob["score"] == 1
