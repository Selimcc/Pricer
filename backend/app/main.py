from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db import get_db
from app.models import Product, Store, PriceObservation, ObservationVote
from app.schemas import ProductOut, ObservationCreate, VoteCreate
from app.services.scoring import haversine_km, confidence_for
from app.services.openfoodfacts import lookup_ean
from app.seed import seed

app = FastAPI(
    title="Grocery Waze API",
    version="0.2.0",
    description="Local prototype for community-powered grocery price comparison.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_origins == "*" else settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    seed()


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(select(func.count()).select_from(Product))
        return {"status": "ok", "database": "ok"}
    except SQLAlchemyError:
        return {"status": "degraded", "database": "error"}


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    products = db.scalar(select(func.count()).select_from(Product)) or 0
    stores = db.scalar(select(func.count()).select_from(Store)) or 0
    observations = db.scalar(select(func.count()).select_from(PriceObservation)) or 0
    votes = db.scalar(select(func.count()).select_from(ObservationVote)) or 0
    return {"products": products, "stores": stores, "observations": observations, "votes": votes}


@app.get("/observations/recent")
def recent_observations(limit: int = Query(12, ge=1, le=50), db: Session = Depends(get_db)):
    observations = db.scalars(
        select(PriceObservation).order_by(PriceObservation.observed_at.desc()).limit(limit)
    ).all()
    result = []
    for obs in observations:
        product = db.get(Product, obs.product_id)
        store = db.get(Store, obs.store_id)
        if not product or not store:
            continue
        confirmations = db.scalar(select(func.count()).select_from(ObservationVote).where(
            ObservationVote.observation_id == obs.id, ObservationVote.vote == 1
        )) or 0
        rejections = db.scalar(select(func.count()).select_from(ObservationVote).where(
            ObservationVote.observation_id == obs.id, ObservationVote.vote == -1
        )) or 0
        confidence, _ = confidence_for(obs.observed_at, confirmations, rejections)
        result.append({
            "id": obs.id,
            "product": product.name,
            "brand": product.brand,
            "store": store.name,
            "chain": store.chain,
            "price": float(obs.price),
            "promotion": obs.promotion_label if obs.is_promotion else None,
            "observed_at": obs.observed_at,
            "confidence": confidence,
            "confirmations": confirmations,
            "rejections": rejections,
        })
    return result


@app.get("/stores",)
def stores(db: Session = Depends(get_db)):
    return [
        {
            "id": s.id,
            "chain": s.chain,
            "name": s.name,
            "address": s.address,
            "city": s.city,
            "latitude": s.latitude,
            "longitude": s.longitude,
        }
        for s in db.scalars(select(Store).order_by(Store.chain, Store.name)).all()
    ]


@app.get("/products/{ean}", response_model=ProductOut)
async def get_product(ean: str, db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.ean == ean))

    if product:
        return product

    external = await lookup_ean(ean)

    if not external:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    product = Product(ean=ean, **external)
    db.add(product)
    db.commit()
    db.refresh(product)

    return product


@app.get("/products/{ean}/suggestions")
def product_suggestions(
    ean: str,
    limit: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
):
    clean_ean = "".join(c for c in ean if c.isdigit())

    if not clean_ean:
        return []

    products = db.scalars(select(Product)).all()
    candidates = []

    for product in products:
        candidate_ean = "".join(
            c for c in product.ean if c.isdigit()
        )

        if not candidate_ean:
            continue

        length_penalty = abs(
            len(clean_ean) - len(candidate_ean)
        )

        common_length = min(
            len(clean_ean),
            len(candidate_ean)
        )

        digit_distance = sum(
            clean_ean[i] != candidate_ean[i]
            for i in range(common_length)
        )

        prefix_length = 0

        for a, b in zip(clean_ean, candidate_ean):
            if a != b:
                break
            prefix_length += 1

        if length_penalty == 0 and (
            prefix_length >= 4 or digit_distance <= 3
        ):
            candidates.append({
                "product": product,
                "prefix_length": prefix_length,
                "digit_distance": digit_distance,
                "length_penalty": length_penalty,
            })

    candidates.sort(
        key=lambda x: (
            -x["prefix_length"],
            x["digit_distance"],
            x["length_penalty"],
        )
    )

    return [
        {
            "id": item["product"].id,
            "ean": item["product"].ean,
            "name": item["product"].name,
            "brand": item["product"].brand,
            "quantity": item["product"].quantity,
            "image_url": item["product"].image_url,
        }
        for item in candidates[:limit]
    ]


@app.get("/stores/nearby")
def nearby_stores(
    latitude: float,
    longitude: float,
    radius_km: float = Query(5, gt=0, le=50),
    db: Session = Depends(get_db),
):
    stores = db.scalars(select(Store)).all()
    result = []
    for s in stores:
        distance = haversine_km(latitude, longitude, s.latitude, s.longitude)
        if distance is not None and distance <= radius_km:
            result.append({
                "id": s.id,
                "chain": s.chain,
                "name": s.name,
                "address": s.address,
                "city": s.city,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "distance_km": round(distance, 2),
            })
    return sorted(result, key=lambda x: x["distance_km"])


@app.get("/products/{ean}/comparison")
def comparison(
    ean: str,
    latitude: float = 48.8566,
    longitude: float = 2.3522,
    radius_km: float = Query(10, gt=0, le=50),
    db: Session = Depends(get_db),
):
    product = db.scalar(select(Product).where(Product.ean == ean))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    observations = db.scalars(
        select(PriceObservation)
        .where(PriceObservation.product_id == product.id)
        .order_by(PriceObservation.price.asc())
    ).all()

    result = []
    for obs in observations:
        store = db.get(Store, obs.store_id)
        if not store:
            continue
        distance = haversine_km(latitude, longitude, store.latitude, store.longitude)
        if distance is not None and distance > radius_km:
            continue

        confirmations = db.scalar(select(func.count()).select_from(ObservationVote).where(
            ObservationVote.observation_id == obs.id, ObservationVote.vote == 1
        )) or 0
        rejections = db.scalar(select(func.count()).select_from(ObservationVote).where(
            ObservationVote.observation_id == obs.id, ObservationVote.vote == -1
        )) or 0
        confidence, confirmation_score = confidence_for(obs.observed_at, confirmations, rejections)

        result.append({
            "observation_id": obs.id,
            "store_id": store.id,
            "store_name": store.name,
            "chain": store.chain,
            "price": float(obs.price),
            "is_promotion": obs.is_promotion,
            "promotion_label": obs.promotion_label,
            "observed_at": obs.observed_at,
            "distance_km": round(distance, 2) if distance is not None else None,
            "confirmations": confirmations,
            "rejections": rejections,
            "confirmation_score": confirmation_score,
            "confidence": confidence,
        })

    result.sort(key=lambda x: x["price"])
    best_price = result[0]["price"] if result else None
    for index, row in enumerate(result):
        row["rank"] = index + 1
        row["savings_vs_best"] = round(row["price"] - best_price, 2) if best_price is not None else 0
    return {
        "product": ProductOut.model_validate(product),
        "results": result,
        "best_price": best_price,
        "store_count": len(result),
    }


@app.post("/observations")
def create_observation(payload: ObservationCreate, db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.ean == payload.ean))
    if not product:
        raise HTTPException(status_code=404, detail="Unknown product. Scan/resolve it first.")
    store = db.get(Store, payload.store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    if payload.latitude is not None and payload.longitude is not None:
        distance = haversine_km(payload.latitude, payload.longitude, store.latitude, store.longitude)
        if distance is not None and distance > 2.0:
            raise HTTPException(status_code=400, detail=f"Location is {distance:.1f} km from this store. Prototype limit: 2 km.")

    obs = PriceObservation(
        product_id=product.id, store_id=store.id, user_id=payload.user_id,
        price=payload.price, is_promotion=payload.is_promotion,
        promotion_label=payload.promotion_label, proof_image_url=payload.proof_image_url,
        latitude=payload.latitude, longitude=payload.longitude,
    )
    db.add(obs)
    db.commit()
    db.refresh(obs)
    return {"id": obs.id, "status": "created"}


@app.post("/observations/{observation_id}/vote")
def vote_observation(observation_id: int, payload: VoteCreate, db: Session = Depends(get_db)):
    obs = db.get(PriceObservation, observation_id)
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    if payload.vote not in (-1, 1):
        raise HTTPException(status_code=400, detail="Vote must be -1 or 1")
    existing = db.scalar(select(ObservationVote).where(
        ObservationVote.observation_id == observation_id,
        ObservationVote.user_id == payload.user_id,
    ))
    if existing:
        existing.vote = payload.vote
    else:
        db.add(ObservationVote(observation_id=observation_id, user_id=payload.user_id, vote=payload.vote))
    db.commit()
    return {"status": "ok"}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


DASHBOARD_HTML = r'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grocery Waze — Local Dashboard</title>
<style>
:root{font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:#171a1f;background:#f4f6f8}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1180px;margin:auto;padding:32px 20px}.top{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:24px}.eyebrow{color:#247a55;font-weight:800;letter-spacing:.08em;font-size:12px}.title{font-size:34px;font-weight:900;margin:5px 0}.sub{color:#667085}.status{background:#e8f7ef;color:#187447;border-radius:999px;padding:9px 13px;font-weight:700}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.stat{background:white;border:1px solid #e7e9ed;border-radius:18px;padding:20px;box-shadow:0 6px 24px #1018280a}.stat b{display:block;font-size:30px;margin-top:5px}.label{color:#667085;font-size:13px}.panel{background:white;border:1px solid #e7e9ed;border-radius:20px;margin-top:18px;padding:20px;box-shadow:0 6px 24px #1018280a}.panel h2{margin:0 0 14px}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;padding:12px 8px;border-bottom:1px solid #eef0f2;font-size:14px}.pill{display:inline-flex;border-radius:999px;padding:5px 8px;background:#eef7f1;color:#247a55;font-weight:700;font-size:12px}.promo{background:#fff3d9;color:#9a6500}.mono{font-variant-numeric:tabular-nums}.muted{color:#667085}.actions{display:flex;gap:10px}.btn{border:0;border-radius:12px;padding:10px 14px;background:#171a1f;color:white;font-weight:800;cursor:pointer}.btn.secondary{background:#edf0f2;color:#171a1f}@media(max-width:800px){.grid{grid-template-columns:repeat(2,1fr)}.top{align-items:start;flex-direction:column}.table{font-size:12px}.hide-mobile{display:none}}
</style></head><body><main class="wrap"><div class="top"><div><div class="eyebrow">GROCERY WAZE / LOCAL</div><div class="title">Centre de contrôle</div><div class="sub">Données du prototype, relevés communautaires et qualité des prix.</div></div><div class="actions"><span id="status" class="status">Connexion…</span><button class="btn secondary" onclick="load()">Actualiser</button></div></div>
<div class="grid"><div class="stat"><span class="label">Produits</span><b id="products">—</b></div><div class="stat"><span class="label">Magasins</span><b id="stores">—</b></div><div class="stat"><span class="label">Relevés</span><b id="observations">—</b></div><div class="stat"><span class="label">Votes</span><b id="votes">—</b></div></div>
<section class="panel"><h2>Derniers relevés</h2><div style="overflow:auto"><table class="table"><thead><tr><th>Produit</th><th>Magasin</th><th>Prix</th><th>Promo</th><th>Fiabilité</th><th class="hide-mobile">Confirmations</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section class="panel"><h2>Architecture locale</h2><p class="muted">Téléphone → FastAPI → PostgreSQL/PostGIS. Le dashboard utilise la même API que l’application mobile. PostgreSQL n’est jamais exposé au téléphone.</p><code>http://localhost:8000/docs</code></section></main>
<script>async function load(){try{let s=await fetch('/stats').then(r=>r.json());for(let k of ['products','stores','observations','votes'])document.getElementById(k).textContent=s[k];let r=await fetch('/observations/recent').then(x=>x.json());document.getElementById('rows').innerHTML=r.map(x=>`<tr><td><b>${x.product}</b><br><span class="muted">${x.brand||''}</span></td><td>${x.chain}<br><span class="muted">${x.store}</span></td><td class="mono"><b>${x.price.toFixed(2)} €</b></td><td>${x.promotion?`<span class="pill promo">${x.promotion}</span>`:'—'}</td><td><span class="pill">${x.confidence}%</span></td><td class="hide-mobile">👍 ${x.confirmations} &nbsp; 👎 ${x.rejections}</td></tr>`).join('');document.getElementById('status').textContent='API connectée';}catch(e){document.getElementById('status').textContent='API indisponible';document.getElementById('status').style.background='#feeceb';document.getElementById('status').style.color='#b42318'}}load();setInterval(load,15000)</script></body></html>'''
