"""Les enseignes dont on lit les prix en ligne, et comment trouver une page produit.

Trois façons de trouver la page d'un code-barres, de la plus directe à la plus indirecte :
- `direct` : l'adresse contient le code-barres (e.leclerc/fp/<EAN>) ;
- `search` : la page de recherche du site renvoie un lien qui contient le code-barres ;
- `sitemap` : on cherche dans les sitemaps (listes de pages publiées pour les moteurs
  de recherche) les pages dont le nom ressemble au produit, puis on vérifie l'EAN
  dans la page avant d'accepter le prix.
"""
import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Retailer:
    key: str
    site: str
    base_url: str
    # Noms d'enseigne OpenStreetMap auxquels ce prix s'applique
    chain_re: re.Pattern
    direct: Callable[[str], str] | None = None
    search: Callable[[str], str] | None = None
    link_re: str | None = None  # motif d'un lien produit dans la page de recherche ({ean} remplacé)
    sitemap_url: str | None = None  # None : sitemaps annoncés dans robots.txt
    use_sitemaps: bool = False
    product_path_re: re.Pattern | None = None
    ean_in_url_re: re.Pattern | None = None

    @property
    def label(self) -> str:
        return f"Prix {self.site}"

    def applies_to(self, chain: str | None) -> bool:
        return bool(chain) and self.chain_re.search(chain.strip()) is not None

    def ean_from_url(self, url: str) -> str | None:
        if not self.ean_in_url_re:
            return None
        m = self.ean_in_url_re.search(url.split("?", 1)[0].rstrip("/"))
        return m.group(1) if m else None


RETAILERS: dict[str, Retailer] = {r.key: r for r in [
    Retailer(
        key="carrefour", site="carrefour.fr", base_url="https://www.carrefour.fr",
        # Hyper et Market ; les formats de proximité (City, Express…) ont leurs propres prix
        chain_re=re.compile(r"^carrefour(?!\s*(city|express|contact|montagne|bio|drive))", re.I),
        search=lambda ean: f"https://www.carrefour.fr/s?q={ean}",
        link_re=r'href="(/p/[^"#?]*-{ean})"',
        ean_in_url_re=re.compile(r"/p/[^/]*-(\d{8,14})$"),
    ),
    Retailer(
        key="leclerc", site="e.leclerc", base_url="https://www.e.leclerc",
        chain_re=re.compile(r"leclerc", re.I),
        direct=lambda ean: f"https://www.e.leclerc/fp/{ean}",
        ean_in_url_re=re.compile(r"/fp/(\d{8,14})$"),
    ),
    Retailer(
        key="auchan", site="auchan.fr", base_url="https://www.auchan.fr",
        chain_re=re.compile(r"^auchan", re.I),
        sitemap_url="https://www.auchan.fr/sitemaps/sitemap-products.xml", use_sitemaps=True,
    ),
    Retailer(
        key="monoprix", site="courses.monoprix.fr", base_url="https://courses.monoprix.fr",
        chain_re=re.compile(r"^monop", re.I),
        sitemap_url="https://courses.monoprix.fr/sitemaps/sitemap_index.xml", use_sitemaps=True,
        product_path_re=re.compile(r"/products/"),
    ),
    Retailer(
        key="franprix", site="franprix.fr", base_url="https://www.franprix.fr",
        chain_re=re.compile(r"^franprix", re.I),
        use_sitemaps=True,
    ),
]}
