"""Import complet d'Open Prices pour une zone (par défaut l'Île-de-France).

L'API n'interroge Open Prices que produit par produit, au moment d'un scan.
Cette tâche télécharge leur export quotidien (tous les prix, licence ODbL) et
importe d'un coup tous les prix récents de la zone : les magasins autour de
l'utilisateur ont des prix avant même le premier scan.

    docker compose exec api python -m app.jobs.open_prices_import
    docker compose exec api python -m app.jobs.open_prices_import --bbox 48.80,2.10,48.95,2.35 --days 180
"""
import argparse
import gzip
import json
import os
import time
from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import SessionLocal
from app.models import PriceObservation, Product
from app.services.ean import normalize_ean
from app.services.osm import get_or_create_osm_store
from app.services.providers.open_prices import parse_price_item

# Fiche minimale créée à l'import ; complétée (photo, marque, contenance) au premier scan
STUB_SOURCE = "op_import"
BATCH = 1000


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    lat_min, lon_min, lat_max, lon_max = (float(x) for x in text.split(","))
    return lat_min, lon_min, lat_max, lon_max


def download(url: str, target: Path, max_age_h: float = 20) -> Path:
    """Télécharge l'export (quelques dizaines de Mo) sauf s'il est récent."""
    if target.exists() and time.time() - target.stat().st_mtime < max_age_h * 3600:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    with httpx.stream("GET", url, headers={"User-Agent": settings.http_user_agent},
                      timeout=httpx.Timeout(60.0, read=300.0), follow_redirects=True) as response:
        response.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in response.iter_bytes(1 << 20):
                f.write(chunk)
    os.replace(tmp, target)
    return target


def read_jsonl(path: Path) -> Iterator[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def normalize_item(item: dict) -> dict:
    """L'export peut être « à plat » (location_osm_id…) ou imbriqué comme l'API : on ramène à l'API."""
    if not isinstance(item.get("location"), dict) and item.get("location_osm_id"):
        display = item.get("location_osm_display_name") or ""
        item = {**item, "location": {
            "type": item.get("location_type") or "OSM",
            "osm_id": item.get("location_osm_id"),
            "osm_type": item.get("location_osm_type"),
            "osm_lat": item.get("location_osm_lat"),
            "osm_lon": item.get("location_osm_lon"),
            "osm_name": item.get("location_osm_name") or display.split(",")[0].strip() or None,
            "osm_brand": item.get("location_osm_brand"),
            "osm_address_city": item.get("location_osm_address_city"),
            "osm_address_postcode": item.get("location_osm_address_postcode"),
            "osm_tag_value": item.get("location_osm_tag_value"),
        }}
    if not isinstance(item.get("proof"), dict) and item.get("proof_file_path"):
        item = {**item, "proof": {"file_path": item["proof_file_path"]}}
    if isinstance(item.get("product"), dict) and not item.get("product_name"):
        item = {**item, "product_name": item["product"].get("product_name")}
    return item


def in_bbox(item: dict, bbox: tuple[float, float, float, float]) -> bool:
    loc = item.get("location") or {}
    lat, lon = loc.get("osm_lat"), loc.get("osm_lon")
    if lat is None or lon is None:
        return False
    return bbox[0] <= float(lat) <= bbox[2] and bbox[1] <= float(lon) <= bbox[3]


def import_items(db: Session, items: Iterable[dict], bbox: tuple[float, float, float, float],
                 since: date) -> dict:
    stats = {"read": 0, "in_area": 0, "imported": 0, "stores": 0, "new_products": 0}
    stores: dict[tuple[str, int], int] = {}
    products: dict[str, int] = {}
    batch: list[dict] = []

    def product_id(ean: str, name: str | None) -> int:
        if ean not in products:
            pid = db.scalar(select(Product.id).where(Product.ean == ean))
            if pid is None:
                stub = Product(ean=ean, name=(name or f"Produit {ean}")[:255], source=STUB_SOURCE)
                db.add(stub)
                db.flush()
                pid = stub.id
                stats["new_products"] += 1
            products[ean] = pid
        return products[ean]

    def flush():
        nonlocal batch
        if batch:
            result = db.execute(insert(PriceObservation).values(batch)
                                .on_conflict_do_nothing(constraint="uq_observations_source_external")
                                .returning(PriceObservation.id))
            stats["imported"] += len(result.all())
            db.commit()
            batch = []

    for raw in items:
        stats["read"] += 1
        item = normalize_item(raw)
        if not in_bbox(item, bbox) or (item.get("date") or "") < since.isoformat():
            continue
        ean = normalize_ean(str(item.get("product_code") or ""))
        parsed = parse_price_item(item) if ean else None
        if not parsed:
            continue
        stats["in_area"] += 1
        store_data, obs = parsed
        key = (store_data["osm_type"], store_data["osm_id"])
        if key not in stores:
            stores[key] = get_or_create_osm_store(db, store_data).id
        batch.append({**obs, "product_id": product_id(ean, item.get("product_name")), "store_id": stores[key]})
        if len(batch) >= BATCH:
            flush()
    flush()
    stats["stores"] = len(stores)
    return stats


def run(bbox_text: str | None = None, days: int | None = None, file: str | None = None) -> dict:
    bbox = parse_bbox(bbox_text or settings.import_bbox)
    since = (datetime.now(timezone.utc) - timedelta(days=days or settings.open_prices_import_days)).date()
    path = Path(file) if file else download(settings.open_prices_export_url,
                                            Path(settings.data_dir) / "open-prices" / "prices.jsonl.gz")
    db = SessionLocal()
    try:
        stats = import_items(db, read_jsonl(path), bbox, since)
    finally:
        db.close()
    print(f"[open_prices_import] {stats['read']} prix lus, {stats['in_area']} dans la zone, "
          f"{stats['imported']} nouveaux, {stats['stores']} magasins, {stats['new_products']} nouveaux produits")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Importe les prix Open Prices d'une zone.")
    parser.add_argument("--bbox", help="lat_min,lon_min,lat_max,lon_max (défaut : IMPORT_BBOX)")
    parser.add_argument("--days", type=int, help="ancienneté max des prix (défaut : OPEN_PRICES_IMPORT_DAYS)")
    parser.add_argument("--file", help="export déjà téléchargé (.jsonl ou .jsonl.gz)")
    args = parser.parse_args()
    run(args.bbox, args.days, args.file)


if __name__ == "__main__":
    main()
