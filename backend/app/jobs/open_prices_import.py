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


def location_from_row(row: dict, prefix: str = "") -> dict | None:
    """Ligne de l'export des magasins (ou colonnes « location_* ») -> magasin au format de l'API."""
    def get(key):
        return row.get(prefix + key)

    if (get("type") or "OSM") != "OSM" or not get("osm_id") or get("osm_lat") is None or get("osm_lon") is None:
        return None  # magasins en ligne ou sans coordonnées
    display = get("osm_display_name") or ""
    return {
        "type": "OSM",
        "osm_id": get("osm_id"),
        "osm_type": get("osm_type"),
        "osm_lat": float(get("osm_lat")),
        "osm_lon": float(get("osm_lon")),
        "osm_name": get("osm_name") or display.split(",")[0].strip() or None,
        "osm_brand": get("osm_brand"),
        "osm_address_city": get("osm_address_city"),
        "osm_address_postcode": get("osm_address_postcode"),
        "osm_tag_value": get("osm_tag_value"),
    }


def load_locations(path: Path, bbox: tuple[float, float, float, float]) -> dict[int, dict]:
    """Magasins de l'export, seulement ceux de la zone : id Open Prices -> magasin."""
    result = {}
    for row in read_jsonl(path):
        loc = location_from_row(row)
        if loc and row.get("id") is not None and in_bbox({"location": loc}, bbox):
            result[int(row["id"])] = loc
    return result


def load_proofs(path: Path, wanted: set[int]) -> dict[int, str]:
    """Photos de preuve utiles. Les tickets de caisse (données personnelles) ne sont pas repris."""
    result = {}
    for row in read_jsonl(path):
        pid = row.get("id")
        if pid in wanted and row.get("file_path") and (row.get("type") or "") != "RECEIPT":
            result[int(pid)] = row["file_path"]
    return result


def _ref(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def normalize_item(item: dict, locations: dict[int, dict] | None = None,
                   proofs: dict[int, str] | None = None) -> dict:
    """Ramène un prix au format de l'API (magasin et preuve imbriqués), quel que soit le format de l'export :
    imbriqué (API), « à plat » (colonnes location_osm_*) ou par identifiants (location_id, proof_id)."""
    loc = item.get("location")
    if not isinstance(loc, dict):
        if item.get("location_osm_lat") is not None:
            loc = location_from_row(item, "location_")
        elif locations is not None:
            loc = locations.get(_ref(item.get("location_id")) or _ref(loc))
        else:
            loc = None
        item = {**item, "location": loc}
    proof = item.get("proof")
    if not isinstance(proof, dict):
        path = item.get("proof_file_path") if (item.get("proof_type") or "") != "RECEIPT" else None
        if not path and proofs:
            path = proofs.get(_ref(item.get("proof_id")) or _ref(proof))
        item = {**item, "proof": {"file_path": path} if path else None}
    if isinstance(item.get("product"), dict) and not item.get("product_name"):
        item = {**item, "product_name": item["product"].get("product_name")}
    return item


def in_bbox(item: dict, bbox: tuple[float, float, float, float]) -> bool:
    loc = item.get("location")
    if not isinstance(loc, dict):
        return False
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


def export_url(name: str) -> str:
    return settings.open_prices_export_url.rsplit("/", 1)[0] + f"/{name}.jsonl.gz"


def run(bbox_text: str | None = None, days: int | None = None, file: str | None = None) -> dict:
    bbox = parse_bbox(bbox_text or settings.import_bbox)
    since = (datetime.now(timezone.utc) - timedelta(days=days or settings.open_prices_import_days)).date()
    folder = Path(settings.data_dir) / "open-prices"
    path = Path(file) if file else download(settings.open_prices_export_url, folder / "prices.jsonl.gz")

    # L'export des prix ne contient que l'identifiant du magasin et de la preuve : on joint les deux autres exports
    locations = None
    if not file:
        locations = load_locations(download(export_url("locations"), folder / "locations.jsonl.gz"), bbox)
        print(f"[open_prices_import] {len(locations)} magasins Open Prices dans la zone", flush=True)

    read = 0
    selected = []
    for raw in read_jsonl(path):
        read += 1
        item = normalize_item(raw, locations)
        if in_bbox(item, bbox) and (item.get("date") or "") >= since.isoformat():
            selected.append(raw | {"location": item["location"]})

    proofs: dict[int, str] = {}
    wanted = {_ref(i.get("proof_id")) or _ref(i.get("proof")) for i in selected} - {None}
    if wanted and not file:
        try:
            proofs = load_proofs(download(export_url("proofs"), folder / "proofs.jsonl.gz"), wanted)
        except Exception as exc:  # les photos sont un plus : l'import continue sans
            print(f"[open_prices_import] preuves indisponibles : {exc}")

    db = SessionLocal()
    try:
        stats = import_items(db, (normalize_item(i, locations, proofs) for i in selected), bbox, since)
    finally:
        db.close()
    stats["read"] = read
    print(f"[open_prices_import] {read} prix lus, {stats['in_area']} dans la zone, "
          f"{stats['imported']} nouveaux, {stats['stores']} magasins, {stats['new_products']} nouveaux produits",
          flush=True)
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
