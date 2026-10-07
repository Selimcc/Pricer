"""Indexation des sitemaps des enseignes (pages produit publiées pour les robots)."""
import gzip
import html
import re
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import OnlineCatalogUrl, OnlineRetailerState
from app.services.online.http import PoliteClient
from app.services.online.matching import slug_of
from app.services.online.retailers import Retailer

LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
PRODUCT_HINT = re.compile(r"produ|article", re.IGNORECASE)
MAX_FILES = 120


def _decode(page) -> str:
    data = page.content or page.text.encode()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="replace")


def sitemap_product_urls(client: PoliteClient, retailer: Retailer, max_files: int = MAX_FILES):
    """Toutes les adresses de pages produit (générateur, un fichier à la fois)."""
    if retailer.sitemap_url:
        queue = [retailer.sitemap_url]
    else:
        _, maps = client.robots(retailer.base_url)
        queue = list(maps)
    seen = set()
    while queue and len(seen) < max_files:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        text = _decode(client.get(url))
        locs = [html.unescape(x) for x in LOC_RE.findall(text)]
        if "<sitemapindex" in text[:2000].lower():
            children = [u for u in locs if PRODUCT_HINT.search(u.rsplit("/", 1)[-1])] or locs
            queue.extend(children)
            continue
        for loc in locs:
            if retailer.product_path_re is None or retailer.product_path_re.search(loc):
                yield loc


def index_retailer(db: Session, client: PoliteClient, retailer: Retailer) -> int:
    started = datetime.now(timezone.utc)
    batch: list[dict] = []
    total = 0

    def flush():
        nonlocal batch
        if not batch:
            return
        rows = list({r["url"]: r for r in batch}.values())
        stmt = insert(OnlineCatalogUrl).values(rows)
        db.execute(stmt.on_conflict_do_update(
            constraint="uq_online_catalog_url",
            set_={"slug": stmt.excluded.slug, "indexed_at": stmt.excluded.indexed_at,
                  "ean": func.coalesce(stmt.excluded.ean, OnlineCatalogUrl.ean)},
        ))
        db.commit()
        batch = []

    for url in sitemap_product_urls(client, retailer):
        batch.append({"retailer": retailer.key, "url": url, "slug": slug_of(url),
                      "ean": retailer.ean_from_url(url), "indexed_at": started})
        total += 1
        if len(batch) >= 2000:
            flush()
    flush()
    if total:
        # Pages disparues des sitemaps
        db.execute(delete(OnlineCatalogUrl).where(
            OnlineCatalogUrl.retailer == retailer.key, OnlineCatalogUrl.indexed_at < started))
    state = db.get(OnlineRetailerState, retailer.key) or OnlineRetailerState(retailer=retailer.key)
    state.sitemap_indexed_at = started
    state.last_status = f"sitemap : {total} pages produit"
    state.updated_at = datetime.now(timezone.utc)
    db.merge(state)
    db.commit()
    return total


def indexed_count(db: Session, retailer: str) -> int:
    return db.scalar(select(func.count()).select_from(OnlineCatalogUrl).where(
        OnlineCatalogUrl.retailer == retailer)) or 0
