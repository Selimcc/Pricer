"""Diagnostic : que donnent les sites des enseignes depuis ce PC ?

Pour chaque enseigne : robots.txt, puis quelques produits connus. Chaque page
reçue est enregistrée dans data/probe/<enseigne>/ pour ajuster les lecteurs,
et un résumé est affiché. Rythme lent, robots.txt respecté, arrêt immédiat
d'une enseigne qui bloque.

    docker compose exec api python -m app.jobs.probe
    docker compose exec api python -m app.jobs.probe carrefour leclerc
"""
import argparse
import json
import re
from pathlib import Path

from app.core.config import settings
from app.services.online import http
from app.services.online.matching import normalize
from app.services.online.parse import find_offer, products_from_jsonld
from app.services.online.retailers import RETAILERS, Retailer
from app.services.online.sitemaps import LOC_RE, _decode

SAMPLES = [
    ("3274080005003", "cristaline eau de source 1 5l"),
    ("3017620422003", "nutella pate a tartiner 400g"),
    ("5449000000996", "coca cola"),
]


def save(folder: Path, name: str, page: http.Page) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80] + ".html")
    path.write_text(f"<!-- {page.status} {page.url} -->\n{page.text}", encoding="utf-8")
    return str(path.relative_to(folder.parent.parent))


def describe(page: http.Page, ean: str, r: Retailer | None = None) -> dict:
    products = products_from_jsonld(page.text)
    offer = find_offer(page.text, ean) or (r.extract(page.text, ean) if r and r.extract else None)
    return {
        "status": page.status,
        "url": page.url,
        "taille": len(page.text),
        "jsonld_produits": len(products),
        "gtins": sorted({g for p in products for g in p.gtins})[:5],
        "prix_lu": str(offer.price) if offer else None,
        "ean_dans_page": ean in page.text,
    }


def probe_retailer(client: http.PoliteClient, r: Retailer, out: Path) -> dict:
    folder = out / r.key
    report: dict = {"enseigne": r.key, "pages": []}
    try:
        rules, sitemaps = client.robots(r.base_url)
        report["sitemaps_robots"] = sitemaps[:10]
        for ean, words in SAMPLES:
            if r.direct:
                page = client.get(r.direct(ean))
                report["pages"].append({"type": "fiche", "ean": ean, "fichier": save(folder, f"fiche-{ean}", page),
                                        **describe(page, ean, r)})
            elif r.search:
                page = client.get(r.search(ean))
                links = re.findall(r.link_re.format(ean=ean), page.text) if r.link_re else []
                report["pages"].append({"type": "recherche", "ean": ean, "liens_produit": links[:3],
                                        "fichier": save(folder, f"recherche-{ean}", page), **describe(page, ean, r)})
                if links:
                    page = client.get(r.base_url + links[0])
                    report["pages"].append({"type": "fiche", "ean": ean,
                                            "fichier": save(folder, f"fiche-{ean}", page), **describe(page, ean, r)})
        if r.use_sitemaps:
            first = r.sitemap_url or (sitemaps[0] if sitemaps else None)
            if not first:
                report["sitemap"] = "aucun sitemap trouvé"
            else:
                page = client.get(first)
                text = _decode(page)
                locs = LOC_RE.findall(text)
                report["sitemap"] = {"url": first, "status": page.status, "entrees": len(locs),
                                     "index": "<sitemapindex" in text[:2000].lower(), "exemples": locs[:8]}
                save(folder, "sitemap-racine", page)
                if report["sitemap"]["index"] and locs:
                    child = next((u for u in locs if re.search(r"produ", u)), locs[0])
                    page = client.get(child)
                    text = _decode(page)
                    locs = LOC_RE.findall(text)
                    report["sitemap_enfant"] = {"url": child, "entrees": len(locs), "exemples": locs[:8]}
                # Une fiche produit au hasard, pour voir comment le prix est décrit
                products = [u for u in locs if r.product_path_re is None or r.product_path_re.search(u)]
                for ean, words in SAMPLES[:1]:
                    target = next((u for u in products if all(w in normalize(u) for w in words.split()[:1])),
                                  products[0] if products else None)
                    if target:
                        page = client.get(target)
                        report["pages"].append({"type": "fiche (sitemap)", "fichier": save(folder, "fiche-sitemap", page),
                                                **describe(page, ean, r)})
        report["verdict"] = verdict(report)
    except http.SiteBlocked as exc:
        report["verdict"] = f"BLOQUÉ : {exc}. On ne contourne pas : enseigne à laisser de côté."
    except http.NotAllowed as exc:
        report["verdict"] = f"INTERDIT par robots.txt : {exc}"
    except Exception as exc:
        report["verdict"] = f"ERREUR {type(exc).__name__}: {exc}"
    return report


def verdict(report: dict) -> str:
    pages = report["pages"]
    if any(p.get("prix_lu") for p in pages):
        return "OK : prix lus depuis la description produit de la page"
    if any(p.get("jsonld_produits") for p in pages):
        return "À ADAPTER : description produit présente mais prix/EAN non reconnus"
    if pages and all(p["status"] == 200 for p in pages):
        return "À ADAPTER : pages reçues mais sans description produit (site en JavaScript ?)"
    return "À VOIR : regarder les fichiers enregistrés"


def main() -> None:
    parser = argparse.ArgumentParser(description="Teste la lecture des prix sur les sites des enseignes.")
    parser.add_argument("retailers", nargs="*", help=f"parmi {', '.join(RETAILERS)} (défaut : toutes)")
    args = parser.parse_args()
    keys = args.retailers or list(RETAILERS)
    out = Path(settings.data_dir) / "probe"
    client = http.PoliteClient(min_delay_s=3.0, daily_cap=60)
    reports = []
    for key in keys:
        r = RETAILERS.get(key)
        if not r:
            print(f"Enseigne inconnue : {key}")
            continue
        print(f"--- {key} ...", flush=True)
        report = probe_retailer(client, r, out)
        reports.append(report)
        print(f"    {report['verdict']}")
        for p in report["pages"]:
            print(f"    {p['type']:16} {p['status']}  jsonld={p['jsonld_produits']}  prix={p['prix_lu']}  {p['url'][:90]}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "resume.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nRésumé complet : data/probe/resume.json (dossier data/ à la racine du projet)")


if __name__ == "__main__":
    main()
