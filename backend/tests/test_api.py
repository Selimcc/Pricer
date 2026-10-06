from app.core.config import settings
from app.models import ObservationVote, PriceObservation
from tests.conftest import HOME

LAT, LON = HOME
NEAR = (48.9480, 2.1460)    # ~130 m
TOWN = (48.9300, 2.1200)    # ~2,6 km
FAR = (48.8566, 2.3522)     # Paris, ~18 km


def q(**kw):
    base = {"latitude": LAT, "longitude": LON}
    base.update(kw)
    return base


# --- Système ------------------------------------------------------------

def test_health_stats_dashboard(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/stats").json()["products"] == 0
    r = client.get("/dashboard")
    assert r.status_code == 200 and "<html" in r.text


# --- Produits -------------------------------------------------------------

def test_invalid_ean_is_rejected(client):
    r = client.get("/products/3017620422004")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invalid_ean"


def test_unknown_product_then_manual_creation(client):
    r = client.get("/products/3254381025887")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "product_not_found"

    r = client.post("/products", json={"ean": "3254381025887", "name": "Lait demi-écrémé", "quantity": "1 L"})
    assert r.status_code == 201
    assert r.json()["quantity_unit"] == "ml" and r.json()["source"] == "user"
    assert client.get("/products/3254381025887").status_code == 200
    assert client.post("/products", json={"ean": "3254381025887", "name": "x" * 3}).status_code == 409


def test_search(client, factory):
    factory.product()
    assert [p["name"] for p in client.get("/products/search", params={"q": "nute"}).json()] == ["Nutella"]


# --- Magasins -------------------------------------------------------------

def test_nearby_stores_use_real_distance(client, factory):
    near = factory.store("Carrefour Market", *NEAR)
    factory.store("Leclerc", *TOWN)
    factory.store("Monoprix", *FAR)
    p = factory.product()
    factory.price(p, near, 4.5)

    stores = client.get("/stores/nearby", params=q(radius_km=5)).json()
    assert [s["chain"] for s in stores] == ["Carrefour Market", "Leclerc"]
    assert 0.1 < stores[0]["distance_km"] < 0.2
    assert stores[0]["price_count"] == 1 and stores[1]["price_count"] == 0

    detail = client.get(f"/stores/{near.id}", params=q()).json()
    assert detail["prices"][0]["product"]["name"] == "Nutella"


# --- Comparaison ----------------------------------------------------------

def test_comparison_one_current_price_per_store(client, factory, db):
    p = factory.product()
    a = factory.store("Carrefour", *NEAR)
    b = factory.store("Leclerc", *TOWN)
    factory.store("Monoprix", *FAR)  # hors rayon

    factory.price(p, a, 4.99, days_ago=10)
    factory.price(p, a, 4.59, days_ago=1)        # prix actuel chez Carrefour
    factory.price(p, b, 4.19, days_ago=2, is_promotion=True, promotion_type="sale", promotion_label="Promotion")
    factory.price(p, b, 3.00, days_ago=200)      # trop ancien, ignoré

    data = client.get(f"/products/{p.ean}/comparison", params=q(radius_km=5)).json()
    assert [(r["chain"], r["price"]) for r in data["results"]] == [("Leclerc", 4.19), ("Carrefour", 4.59)]
    assert data["best_price"] == 4.19
    assert data["potential_savings"] == 0.4
    assert data["results"][1]["savings_vs_best"] == 0.4
    assert data["results"][0]["unit_price"] == 10.48 and data["results"][0]["unit_price_label"] == "€/kg"
    assert data["nearest_store_id"] == a.id
    assert data["results"][0]["confidence_level"] in ("high", "medium", "low")


def test_disputed_price_falls_back_to_previous(client, factory, db):
    p = factory.product()
    a = factory.store("Carrefour", *NEAR)
    factory.price(p, a, 4.79, days_ago=5)
    wrong = factory.price(p, a, 1.00, days_ago=1)
    for u in ("u1", "u2", "u3"):
        db.add(ObservationVote(observation_id=wrong.id, user_id=u, vote=-1))
    db.commit()
    data = client.get(f"/products/{p.ean}/comparison", params=q()).json()
    assert [r["price"] for r in data["results"]] == [4.79]


def test_deal_detection(client, factory):
    p = factory.product()
    stores = [factory.store(f"S{i}", NEAR[0] + i * 0.001, NEAR[1]) for i in range(4)]
    for s in stores[:3]:
        factory.price(p, s, 5.00)
    factory.price(p, stores[3], 3.99)
    data = client.get(f"/products/{p.ean}/comparison", params=q()).json()
    assert data["deal"]["percent"] == 20


# --- Contributions -------------------------------------------------------

def obs_payload(ean, store_id, price="4.29", where=NEAR, user="alice", **kw):
    return {"ean": ean, "store_id": store_id, "price": price, "user_id": user,
            "latitude": where[0], "longitude": where[1], **kw}


def test_create_observation_gps_rules(client, factory):
    p = factory.product()
    s = factory.store("Carrefour", *NEAR)

    r = client.post("/observations", json=obs_payload(p.ean, s.id, where=FAR))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "too_far"

    r = client.post("/observations", json=obs_payload(p.ean, s.id, where=TOWN))
    assert r.status_code == 200 and r.json()["gps_verified"] is False

    r = client.post("/observations", json=obs_payload(p.ean, s.id, user="bob"))
    assert r.json()["gps_verified"] is True and r.json()["status"] == "created"


def test_same_user_correction_updates_instead_of_duplicating(client, factory, db):
    p = factory.product()
    s = factory.store("Carrefour", *NEAR)
    first = client.post("/observations", json=obs_payload(p.ean, s.id, price="4.29")).json()
    second = client.post("/observations", json=obs_payload(p.ean, s.id, price="4.39")).json()
    assert second["status"] == "updated" and second["id"] == first["id"]
    assert db.query(PriceObservation).count() == 1


def test_outlier_price_is_flagged(client, factory):
    p = factory.product()
    s = factory.store("Carrefour", *NEAR)
    for i in range(3):
        factory.price(p, s, 4.5, days_ago=i + 1, user_id=f"u{i}")
    r = client.post("/observations", json=obs_payload(p.ean, s.id, price="45.00")).json()
    assert r["flagged"] is True


def test_promotion_defaults(client, factory, db):
    p = factory.product()
    s = factory.store("Carrefour", *NEAR)
    client.post("/observations", json=obs_payload(p.ean, s.id, is_promotion=True, promotion_type="loyalty",
                                                  regular_price="4.99"))
    obs = db.query(PriceObservation).one()
    assert obs.promotion_label == "Prix fidélité" and float(obs.regular_price) == 4.99


def test_rate_limit(client, factory, monkeypatch):
    monkeypatch.setattr(settings, "max_contributions_per_hour", 2)
    p = factory.product()
    stores = [factory.store(f"S{i}", *NEAR) for i in range(3)]
    codes = [client.post("/observations", json=obs_payload(p.ean, s.id)).status_code for s in stores]
    assert codes == [200, 200, 429]


def test_votes(client, factory):
    p = factory.product()
    s = factory.store("Carrefour", *NEAR)
    o = factory.price(p, s, 4.5, user_id="alice")
    assert client.post(f"/observations/{o.id}/vote", json={"user_id": "alice", "vote": 1}).status_code == 400
    r = client.post(f"/observations/{o.id}/vote", json={"user_id": "bob", "vote": 1}).json()
    assert r["confirmations"] == 1
    r = client.post(f"/observations/{o.id}/vote", json={"user_id": "bob", "vote": -1}).json()
    assert (r["confirmations"], r["rejections"]) == (0, 1)
    assert client.post(f"/observations/{o.id}/vote", json={"user_id": "bob", "vote": 0}).status_code == 422

    data = client.get(f"/products/{p.ean}/comparison", params=q(user_id="bob")).json()
    assert data["results"][0]["my_vote"] == -1


def test_proof_upload(client, factory):
    p = factory.product()
    s = factory.store("Carrefour", *NEAR)
    o = factory.price(p, s, 4.5, user_id="alice")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100

    r = client.post(f"/observations/{o.id}/proof", data={"user_id": "mallory"}, files={"file": ("a.png", png, "image/png")})
    assert r.status_code == 403
    r = client.post(f"/observations/{o.id}/proof", data={"user_id": "alice"}, files={"file": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 415
    r = client.post(f"/observations/{o.id}/proof", data={"user_id": "alice"}, files={"file": ("a.png", png, "image/png")})
    url = r.json()["proof_image_url"]
    assert url.startswith("/uploads/") and client.get(url).content == png

    row = client.get(f"/products/{p.ean}/comparison", params=q()).json()["results"][0]
    assert row["has_proof"] is True


# --- Liste de courses -----------------------------------------------------

def test_shopping_list_and_basket_comparison(client, factory):
    nutella = factory.product()
    coca = factory.product(ean="5449000000996", name="Coca-Cola", quantity_value=1500, quantity_unit="ml")
    milk = factory.product(ean="3254381025887", name="Lait")
    a = factory.store("Carrefour", *NEAR)
    b = factory.store("Leclerc", *TOWN)
    factory.price(nutella, a, 4.50)
    factory.price(coca, a, 2.40)
    factory.price(nutella, b, 4.00)  # Leclerc : pas de prix Coca connu

    uid = "device-123"
    assert client.post(f"/users/{uid}/list", json={"ean": nutella.ean}).status_code == 201
    client.post(f"/users/{uid}/list", json={"ean": nutella.ean})  # quantité 2
    client.post(f"/users/{uid}/list", json={"ean": coca.ean})
    client.post(f"/users/{uid}/list", json={"ean": milk.ean})
    items = client.get(f"/users/{uid}/list").json()
    assert {i["product"]["name"]: i["quantity"] for i in items} == {"Nutella": 2, "Coca-Cola": 1, "Lait": 1}

    data = client.get(f"/users/{uid}/list/comparison", params=q(radius_km=5)).json()
    assert data["priced_items"] == 2 and [u["name"] for u in data["unpriced"]] == ["Lait"]
    leclerc, carrefour = data["stores"]
    assert leclerc["chain"] == "Leclerc"
    # 2 x 4,00 + Coca estimé au prix moyen du secteur (2,40)
    assert leclerc["estimated_total"] == 10.40 and leclerc["missing"][0]["name"] == "Coca-Cola"
    assert carrefour["estimated_total"] == 11.40 and carrefour["coverage"] == 1.0
    assert carrefour["extra_vs_best"] == 1.0
    assert data["split"] == {"total": 10.40, "store_count": 2}

    item_id = next(i["id"] for i in items if i["product"]["name"] == "Lait")
    assert client.patch(f"/users/{uid}/list/{item_id}", json={"checked": True}).json()["checked"] is True
    client.delete(f"/users/{uid}/list")  # retire les articles cochés
    assert len(client.get(f"/users/{uid}/list").json()) == 2
    assert client.delete(f"/users/other-user/list/{items[0]['id']}").status_code == 404


def test_contributions_profile(client, factory, db):
    p = factory.product()
    s = factory.store("Carrefour", *NEAR)
    o = factory.price(p, s, 4.5, user_id="alice")
    db.add(ObservationVote(observation_id=o.id, user_id="bob", vote=1))
    db.commit()
    data = client.get("/users/alice/contributions").json()
    assert data["price_count"] == 1 and data["confirmations_received"] == 1
    assert data["level"]["name"] == "Nouveau venu" and data["level"]["next_at"] == 3
    assert data["recent"][0]["product"] == "Nutella"


def test_history(client, factory):
    p = factory.product()
    s = factory.store("Carrefour", *NEAR)
    factory.price(p, s, 4.9, days_ago=20)
    factory.price(p, s, 4.5, days_ago=2)
    data = client.get(f"/products/{p.ean}/history").json()
    assert [pt["price"] for pt in data["points"]] == [4.9, 4.5]
    assert data["stats"]["min"] == 4.5


def test_store_coordinates_are_indexed(db):
    # L'index géographique doit exister (requêtes « autour de moi »)
    from sqlalchemy import text
    assert db.scalar(text("SELECT count(*) FROM pg_indexes WHERE indexname = 'ix_stores_geog'")) == 1
