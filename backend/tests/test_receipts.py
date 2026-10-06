"""Tickets de caisse : analyse du texte, rapprochement, parcours complet, OCR réel."""
import io
import os
import shutil
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models import PriceObservation, ReceiptLabelMapping
from app.routers import receipts as receipts_router
from app.services.receipts import matching
from app.services.receipts.parser import parse_receipt_text
from tests.conftest import HOME

NOW = datetime(2026, 10, 6, 20, 0, tzinfo=timezone.utc)

CARREFOUR_TICKET = """CARREFOUR MARKET
78600 MAISONS LAFFITTE
TEL 01 39 12 34 56
NUTELLA 400G                 4,19
CRISTALINE 1,5L              0,22 A
LAIT DEMI ECR LACTEL
2 x 1,05
GEL DOUCHE AMANDE  2 X 1,99  3,98
REMISE FIDELITE             -0,50
TOMATES GRAPPE
0,856 kg x 2,99 €/kg         2,56
SOUS-TOTAL                  13,05
TOTAL A PAYER               12,55
CB                          12,55
TVA 5,5%  0,60
05/10/2026 18:42 CAISSE 004
"""

LECLERC_TICKET = """E.LECLERC
3 x PATES BARILLA 500G   3,57 11
SKIP LESSIVE 1,5L        8,99 20
BON DE REDUCTION        -1,00
  2 x 0,89
COCA COLA 33CL           1,78 20
TOTAL                   13,34
LE 06/10/26 A 10H15
"""


# --- Analyse du texte -------------------------------------------------------

def test_parse_carrefour_ticket():
    r = parse_receipt_text(CARREFOUR_TICKET, NOW)
    assert r.chain_key == "carrefour"
    assert r.purchased_at == datetime(2026, 10, 5, 18, 42, tzinfo=timezone.utc)
    assert r.total == Decimal("12.55")
    lines = {ln.label: ln for ln in r.lines}
    assert list(lines) == ["NUTELLA 400G", "CRISTALINE 1,5L", "LAIT DEMI ECR LACTEL", "GEL DOUCHE AMANDE", "TOMATES GRAPPE"]
    assert lines["LAIT DEMI ECR LACTEL"].quantity == 2 and lines["LAIT DEMI ECR LACTEL"].unit_price == Decimal("1.05")
    gel = lines["GEL DOUCHE AMANDE"]
    assert gel.discount == Decimal("0.50") and gel.effective_unit_price == Decimal("1.74")
    tomates = lines["TOMATES GRAPPE"]
    assert tomates.is_weighted and tomates.quantity == Decimal("0.856") and tomates.unit_price == Decimal("2.99")


def test_parse_leclerc_ticket():
    r = parse_receipt_text(LECLERC_TICKET, NOW)
    assert r.chain_key == "leclerc" and r.total == Decimal("13.34")
    assert r.purchased_at.date().isoformat() == "2026-10-06"
    lines = {ln.label: ln for ln in r.lines}
    assert lines["PATES BARILLA 500G"].quantity == 3 and lines["PATES BARILLA 500G"].unit_price == Decimal("1.19")
    assert lines["SKIP LESSIVE 1,5L"].effective_unit_price == Decimal("7.99")
    assert lines["COCA COLA 33CL"].quantity == 2 and lines["COCA COLA 33CL"].unit_price == Decimal("0.89")


def test_old_or_future_dates_are_ignored():
    assert parse_receipt_text("LIDL\nPAIN 1,00\n01/01/2020", NOW).purchased_at is None
    assert parse_receipt_text("LIDL\nPAIN 1,00\n01/01/2027", NOW).purchased_at is None


# --- Rapprochement ----------------------------------------------------------

def test_fuzzy_match_handles_abbreviations(factory, db):
    lait = factory.product(ean="3033490004743", name="Lait demi-écrémé", brand="Lactel", quantity="1 L",
                           quantity_value=1000, quantity_unit="ml")
    factory.product()  # Nutella
    product, source, score = matching.find_match(db, "carrefour", "LAIT DEMI ECR LACTEL")
    assert product.id == lait.id and source == "fuzzy" and score >= 0.6
    assert matching.find_match(db, "carrefour", "PAIN DE CAMPAGNE") == (None, None, None)


# --- Parcours complet --------------------------------------------------------

@pytest.fixture
def fake_ocr(monkeypatch):
    def use(text):
        monkeypatch.setattr(receipts_router, "extract_text", lambda data: text)
    return use


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def upload(client, user="alice", where=HOME):
    return client.post("/receipts", data={"user_id": user, "latitude": str(where[0]), "longitude": str(where[1])},
                       files={"file": ("ticket.png", PNG, "image/png")})


def test_receipt_end_to_end(client, factory, db, fake_ocr):
    fake_ocr(CARREFOUR_TICKET)
    store = factory.store("Carrefour Market", HOME[0] + 0.001, HOME[1])
    factory.store("Lidl", HOME[0], HOME[1] + 0.001)
    nutella = factory.product()
    cristaline = factory.product(ean="3274080005003", name="Cristaline", brand="Cristaline", quantity="1,5 L",
                                 quantity_value=1500, quantity_unit="ml")
    gel = factory.product(ean="3600551054780", name="Gel douche amande", brand="Le Petit Marseillais",
                          quantity="250 ml", quantity_value=250, quantity_unit="ml")
    lait = factory.product(ean="3033490004743", name="Lait 1/2 écrémé", brand="Bridel", quantity="1 L",
                           quantity_value=1000, quantity_unit="ml")

    r = upload(client)
    assert r.status_code == 201
    receipt = r.json()
    assert receipt["store"]["id"] == store.id          # enseigne lue + GPS -> bon magasin
    assert receipt["total"] == 12.55 and receipt["warning"] is None
    lines = {ln["label"]: ln for ln in receipt["lines"]}
    assert lines["NUTELLA 400G"]["product"]["id"] == nutella.id
    assert lines["CRISTALINE 1,5L"]["product"]["id"] == cristaline.id
    assert lines["GEL DOUCHE AMANDE"]["product"]["id"] == gel.id
    assert lines["TOMATES GRAPPE"]["status"] == "ignored"   # au poids : pas encore pris en charge
    assert lines["LAIT DEMI ECR LACTEL"]["product"] is None  # « Bridel » ne ressemble pas assez

    # L'utilisateur associe la ligne de lait en scannant le produit
    rid, lait_line = receipt["id"], lines["LAIT DEMI ECR LACTEL"]["id"]
    r = client.patch(f"/receipts/{rid}/lines/{lait_line}", json={"user_id": "alice", "ean": lait.ean})
    assert r.json()["counts"]["matched"] == 4

    # Le ticket des autres reste privé
    assert client.get(f"/receipts/{rid}", params={"user_id": "mallory"}).status_code == 404

    r = client.post(f"/receipts/{rid}/publish", json={"user_id": "alice"})
    body = r.json()
    assert body["published_now"] == 4 and body["counts"]["published"] == 4
    obs = {o.product_id: o for o in db.query(PriceObservation).all()}
    assert obs[gel.id].price == Decimal("1.74") and obs[gel.id].promotion_type == "loyalty"
    assert obs[gel.id].regular_price == Decimal("1.99")
    assert obs[lait.id].price == Decimal("1.05")
    assert obs[nutella.id].observed_at == datetime(2026, 10, 5, 18, 42, tzinfo=timezone.utc)

    # Le prix apparaît dans la comparaison, avec preuve mais sans exposer l'image du ticket
    # (date d'achat réelle sur le ticket : on la remplace par aujourd'hui pour rester dans la fenêtre)
    obs[nutella.id].observed_at = datetime.now(timezone.utc)
    db.commit()
    row = client.get(f"/products/{nutella.ean}/comparison", params={"latitude": HOME[0], "longitude": HOME[1]}).json()["results"][0]
    assert row["source_label"] == "Ticket de caisse" and row["has_proof"] is True and row["proof_image_url"] is None

    # Republier ne duplique rien
    assert client.post(f"/receipts/{rid}/publish", json={"user_id": "alice"}).json()["published_now"] == 0
    assert db.query(PriceObservation).count() == 4

    # Mémoire collective : le ticket suivant d'un autre utilisateur se remplit tout seul
    assert db.query(ReceiptLabelMapping).filter_by(label_key="LAIT DEMI ECR LACTEL").one().product_id == lait.id
    r = upload(client, user="bob").json()
    lait_bob = next(ln for ln in r["lines"] if ln["label"] == "LAIT DEMI ECR LACTEL")
    assert lait_bob["product"]["id"] == lait.id and lait_bob["match_source"] == "mapping"

    assert client.get("/receipts", params={"user_id": "alice"}).json()[0]["lines"] == 5


def test_store_required_and_manual_choice(client, factory, fake_ocr):
    fake_ocr(LECLERC_TICKET)
    r = client.post("/receipts", data={"user_id": "alice"}, files={"file": ("t.png", PNG, "image/png")}).json()
    assert r["store"] is None and r["detected_chain"] == "leclerc"
    assert client.post(f"/receipts/{r['id']}/publish", json={"user_id": "alice"}).json()["detail"]["code"] == "store_required"
    store = factory.store("E.Leclerc", *HOME)
    r = client.patch(f"/receipts/{r['id']}", json={"user_id": "alice", "store_id": store.id}).json()
    assert r["store"]["chain"] == "E.Leclerc"


def test_unreadable_receipt_warns(client, fake_ocr):
    fake_ocr("@@@ ### illisible")
    r = client.post("/receipts", data={"user_id": "alice"}, files={"file": ("t.png", PNG, "image/png")}).json()
    assert r["lines"] == [] and "Aucune ligne" in r["warning"]


# --- OCR réel ---------------------------------------------------------------

FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"]


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract non installé")
def test_real_ocr_on_generated_receipt():
    from PIL import Image, ImageDraw, ImageFont

    from app.services.receipts.ocr import extract_text

    font_path = next((p for p in FONT_PATHS if os.path.exists(p)), None)
    if not font_path:
        pytest.skip("Aucune police monospace disponible")
    font = ImageFont.truetype(font_path, 26)
    lines = CARREFOUR_TICKET.splitlines()
    img = Image.new("L", (760, 60 + 40 * len(lines)), 255)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((30, 30 + 40 * i), line, font=font, fill=20)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    text = extract_text(buf.getvalue())
    parsed = parse_receipt_text(text, NOW)
    labels = [ln.label for ln in parsed.lines]
    assert parsed.chain_key == "carrefour"
    assert parsed.total == Decimal("12.55")
    assert "NUTELLA 400G" in labels
    assert len(parsed.lines) >= 4
