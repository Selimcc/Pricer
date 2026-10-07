from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ObservationVote, OsmImportArea, PriceObservation, Product, ShoppingListItem, Store

router = APIRouter(tags=["Système"])

API_VERSION = "0.6.0"
DASHBOARD_FILE = Path(__file__).resolve().parent.parent / "static" / "dashboard.html"


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        postgis = db.scalar(text("SELECT postgis_lib_version()"))
        return {"status": "ok", "database": "ok", "postgis": postgis, "version": API_VERSION}
    except SQLAlchemyError:
        return {"status": "degraded", "database": "error", "version": API_VERSION}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    by_source = dict(db.execute(
        select(PriceObservation.source, func.count()).group_by(PriceObservation.source)).all())
    stores_by_source = dict(db.execute(select(Store.source, func.count()).group_by(Store.source)).all())
    return {
        "products": count(Product),
        "stores": count(Store),
        "observations": count(PriceObservation),
        "votes": count(ObservationVote),
        "contributors": db.scalar(select(func.count(func.distinct(PriceObservation.user_id))).where(
            PriceObservation.source == "community")) or 0,
        "list_items": count(ShoppingListItem),
        "osm_areas": count(OsmImportArea),
        "observations_by_source": by_source,
        "stores_by_source": stores_by_source,
        "flagged": count(PriceObservation, PriceObservation.flagged.is_(True)),
        "with_proof": count(PriceObservation, PriceObservation.proof_image_url.is_not(None)),
    }


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    return DASHBOARD_FILE.read_text(encoding="utf-8")
