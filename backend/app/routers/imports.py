"""Imports de prix depuis l'extérieur : panier de la semaine (tâche du jeudi).

Sur le PC (réseau local), pas de clé ; depuis Internet (tunnel), clé exigée comme ailleurs.
La page /imports sert au navigateur de l'app Claude : il colle le JSON et clique « Importer ».
"""
from fastapi import APIRouter, Body, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models import Product, ProductGroup, ProductGroupMember, ShoppingListItem
from app.routers.deps import api_error
from app.services.basket_import import BasketImportError, import_basket

router = APIRouter(prefix="/imports", tags=["Imports"])

WATCHLIST_MAX = 30

PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Pricer · import du panier</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:32px auto;padding:0 16px;color:#14213d}
textarea{width:100%;height:320px;font:13px ui-monospace,monospace}button{margin-top:12px;padding:10px 18px;
background:#14213d;color:#fff;border:0;border-radius:8px;font-size:15px}pre{background:#eef1f6;padding:12px;
border-radius:8px;white-space:pre-wrap}</style></head><body>
<h1>Import du panier de la semaine</h1>
<p>Colle le JSON des prix relevés (format décrit dans <code>backend/app/services/basket_import.py</code>).</p>
<textarea id="payload" aria-label="JSON du panier"></textarea>
<button id="import" type="button">Importer</button>
<pre id="result" aria-live="polite">En attente.</pre>
<script>
document.getElementById("import").addEventListener("click", async () => {
  const out = document.getElementById("result");
  out.textContent = "Import en cours…";
  try {
    const body = JSON.parse(document.getElementById("payload").value);
    const r = await fetch("/imports/basket", {method: "POST", headers: {"Content-Type": "application/json"},
                                              body: JSON.stringify(body)});
    const data = await r.json();
    out.textContent = (r.ok ? "IMPORT OK\\n" : "ERREUR\\n") + JSON.stringify(data, null, 2);
  } catch (e) { out.textContent = "ERREUR\\n" + e; }
});
</script></body></html>"""


@router.get("", response_class=HTMLResponse, include_in_schema=False)
def import_page():
    return PAGE


@router.post("/basket")
def post_basket(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Prix du panier de la semaine : prix en ligne (privés) + produits équivalents."""
    try:
        stats = import_basket(db, payload)
    except BasketImportError as exc:
        raise api_error(422, "invalid_basket", str(exc)) from exc
    stats["visible_in_app"] = settings.enable_online_prices
    return stats


@router.get("/watchlist")
def watchlist(db: Session = Depends(get_db)):
    """Produits de la liste de courses à suivre en plus des lignes du panier (30 max)."""
    items = db.scalars(
        select(Product).join(ShoppingListItem, ShoppingListItem.product_id == Product.id)
        .where(ShoppingListItem.checked.is_(False)).distinct().limit(WATCHLIST_MAX)
    ).all()
    groups = dict(db.execute(
        select(ProductGroupMember.product_id, ProductGroup.name)
        .join(ProductGroup, ProductGroup.id == ProductGroupMember.group_id)
        .where(ProductGroupMember.product_id.in_([p.id for p in items]))
    ).all()) if items else {}
    return [{"ean": p.ean, "name": p.name, "brand": p.brand, "quantity": p.quantity, "line": groups.get(p.id)}
            for p in items]
