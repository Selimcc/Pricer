"""Analyse du texte d'un ticket de caisse français.

Entrée : le texte brut sorti de l'OCR (souvent imparfait).
Sortie : enseigne, date, total, et les lignes d'articles avec quantité,
prix unitaire, total de la ligne et remises.

Formats gérés (les plus courants en grande surface) :
    NUTELLA 400G                 4,19
    NUTELLA 400G            4,19 € 11      (code TVA en fin de ligne)
    2 x 1,29                               (ligne de quantité, avant ou après l'article)
    LAIT DEMI ECR  2 X 1,29      2,58      (quantité sur la même ligne)
    TOMATES GRAPPE
    0,856 kg x 2,99 €/kg         2,56      (article au poids)
    REMISE FIDELITE             -0,50      (remise rattachée à l'article précédent)
    TOTAL A PAYER               7,49
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

CHAINS = [
    # (motif dans le texte, clé d'enseigne)
    (r"CARREFOUR", "carrefour"),
    (r"E\.?\s?LECLERC|LECLERC", "leclerc"),
    (r"AUCHAN", "auchan"),
    (r"INTERMARCH", "intermarche"),
    (r"\bLIDL\b", "lidl"),
    (r"\bALDI\b", "aldi"),
    (r"MONOPRIX", "monoprix"),
    (r"FRANPRIX", "franprix"),
    (r"CASINO", "casino"),
    (r"HYPER\s?U\b|SUPER\s?U\b|U\s?EXPRESS|SYSTEME\s?U", "u"),
    (r"\bNETTO\b", "netto"),
    (r"LEADER\s?PRICE", "leader price"),
    (r"\bCORA\b", "cora"),
    (r"GRAND\s?FRAIS", "grand frais"),
    (r"PICARD", "picard"),
    (r"BIOCOOP", "biocoop"),
    (r"NATURALIA", "naturalia"),
    (r"\bG\s?20\b", "g20"),
    (r"\bSPAR\b", "spar"),
    (r"\bVIVAL\b", "vival"),
    (r"COCCINELLE", "coccinelle"),
]

# Montant en fin de ligne, suivi éventuellement de € et d'un code TVA séparé par un espace
_SUFFIX = r"\s*(?:€|EUR)?(?:\s+(?:[A-Z]|\d{1,2}))?\s*\*?\s*$"
PRICE_END = re.compile(r"(?<![\d,.])(-?\s?\d{1,4}[,.]\d{2})" + _SUFFIX)
QTY_LINE = re.compile(r"^\s*(\d{1,3})\s*[xX×*]\s*(\d{1,4}[,.]\d{2})\s*(?:€|EUR)?\s*(?:/\s*U\w*)?\s*$")
QTY_INLINE = re.compile(r"\s(\d{1,3})\s*[xX×*]\s*(\d{1,4}[,.]\d{2})\s*(?:€|EUR)?\s+(?=-?\d{1,4}[,.]\d{2}" + _SUFFIX + ")")
WEIGHT = re.compile(r"(\d{1,3}[,.]\d{1,3})\s*KG\s*[xX×*]\s*(\d{1,4}[,.]\d{2})\s*(?:€|EUR)?\s*/\s*KG", re.I)
LEADING_QTY = re.compile(r"^\s*(\d{1,3})\s*[xX×*]\s+(?=[A-Za-z])")
LEADING_CODE = re.compile(r"^\s*\d{5,}\s+")
DATE = re.compile(r"\b(\d{2})[/.-](\d{2})[/.-](\d{2}|\d{4})\b(?:\D{0,6}(\d{2})[:hH](\d{2}))?")

DISCOUNT_WORDS = re.compile(r"REMISE|REDUC|PROMO|AVANTAGE|COUPON|BON\s+(?:D|DE)|FIDELIT|IMMEDIAT|OFFRE", re.I)
TOTAL_WORDS = re.compile(r"^\s*(?:TOTAL|MONTANT\s+(?:DU|A\s+PAYER|TTC)|A\s+PAYER|NET\s+A\s+PAYER)\b", re.I)
SUBTOTAL_WORDS = re.compile(r"SOUS[\s-]?TOTAL", re.I)
IGNORE_WORDS = re.compile(
    r"\b(?:TVA|HT|TTC|CB|CARTE|ESPECES|RENDU|MONNAIE|PAIEMENT|ARTICLES?|NB\s?ART|TICKET|CAISSE|CAISSIER|MERCI|"
    r"SIRET|SIREN|TEL|BANCAIRE|VISA|MASTERCARD|CONTACT|AUTORISATION|POINTS|CAGNOTT\w*|SOLDE|DEBIT|CREDIT|"
    r"MAGASIN|BIENVENUE|HORAIRES|WWW|HTTP|NUMERO|TRANSACTION|EMPORTER)\b",
    re.I,
)


@dataclass
class ParsedLine:
    label: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    is_weighted: bool = False
    discount: Decimal | None = None
    discount_label: str | None = None

    @property
    def effective_unit_price(self) -> Decimal:
        """Prix réellement payé à l'unité, remise déduite."""
        total = self.line_total - (self.discount or Decimal(0))
        if self.is_weighted:
            return self.unit_price if not self.discount else (total / self.quantity).quantize(Decimal("0.01"))
        return (total / self.quantity).quantize(Decimal("0.01"))


@dataclass
class ParsedReceipt:
    chain_key: str | None = None
    purchased_at: datetime | None = None
    total: Decimal | None = None
    lines: list[ParsedLine] = field(default_factory=list)


def _money(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(" ", "").replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def detect_chain(text: str) -> str | None:
    head = strip_accents(text.upper())
    for pattern, key in CHAINS:
        if re.search(pattern, head):
            return key
    return None


def detect_date(text: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(timezone.utc)
    for m in DATE.finditer(text):
        d, mo, y, hh, mm = m.groups()
        year = int(y) + (2000 if len(y) == 2 else 0)
        try:
            dt = datetime(year, int(mo), int(d), int(hh or 12), int(mm or 0), tzinfo=timezone.utc)
        except ValueError:
            continue
        if (now - dt).days <= 365 and dt <= now.replace(hour=23, minute=59):
            return dt
    return None


def clean_label(raw: str) -> str:
    label = LEADING_CODE.sub("", raw)
    label = LEADING_QTY.sub("", label)
    label = re.sub(r"[|_*#=~]+", " ", label)
    label = re.sub(r"\s{2,}", " ", label).strip(" .:-")
    return label.upper()


def _letters(s: str) -> int:
    return sum(c.isalpha() for c in s)


def parse_receipt_text(text: str, now: datetime | None = None) -> ParsedReceipt:
    receipt = ParsedReceipt(chain_key=detect_chain(text), purchased_at=detect_date(text, now))
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]

    items: list[ParsedLine] = []
    pending_label: str | None = None      # libellé sans prix (souvent suivi d'une ligne de poids ou de quantité)
    pending_qty: tuple[int, Decimal] | None = None  # « 2 x 1,29 » vu avant l'article

    for raw in lines:
        line = strip_accents(raw)

        if TOTAL_WORDS.search(line) and not SUBTOTAL_WORDS.search(line):
            m = PRICE_END.search(line)
            if m and receipt.total is None:
                receipt.total = _money(m.group(1))
            break  # après le total : paiement, TVA, fidélité… plus d'articles
        if SUBTOTAL_WORDS.search(line):
            continue

        # Article au poids : « 0,856 kg x 2,99 €/kg   2,56 »
        w = WEIGHT.search(line)
        if w:
            m = PRICE_END.search(line)
            weight, per_kg = _money(w.group(1)), _money(w.group(2))
            total = _money(m.group(1)) if m else (weight * per_kg).quantize(Decimal("0.01"))
            before = clean_label(line[: w.start()])
            label = before if _letters(before) >= 3 else pending_label
            if label and weight and per_kg:
                items.append(ParsedLine(label, weight, per_kg, total, is_weighted=True))
            pending_label = None
            continue

        # Ligne de quantité seule : « 2 x 1,29 »
        q = QTY_LINE.match(line)
        if q:
            n, unit = int(q.group(1)), _money(q.group(2))
            prev = items[-1] if items else None
            if prev and prev.quantity == 1 and abs(prev.line_total - n * unit) <= Decimal("0.02"):
                prev.quantity, prev.unit_price = Decimal(n), unit
            elif pending_label:
                items.append(ParsedLine(pending_label, Decimal(n), unit, (n * unit).quantize(Decimal("0.01"))))
                pending_label = None
            else:
                pending_qty = (n, unit)
            continue

        m = PRICE_END.search(line)
        if not m:
            # Libellé sans prix : on le garde pour la ligne suivante (poids, quantité)
            if _letters(line) >= 3 and not IGNORE_WORDS.search(line) and not DISCOUNT_WORDS.search(line):
                pending_label = clean_label(line)
            continue

        amount = _money(m.group(1))
        body = line[: m.start()]
        if amount is None:
            continue

        # Remise : rattachée à l'article précédent
        if (amount < 0 or DISCOUNT_WORDS.search(body)) and items:
            prev = items[-1]
            prev.discount = (prev.discount or Decimal(0)) + abs(amount)
            prev.discount_label = clean_label(body) or "REMISE"
            continue

        if IGNORE_WORDS.search(body) or amount <= 0:
            continue

        qty, unit = 1, amount
        inline = QTY_INLINE.search(line)
        if inline:
            qty, unit = int(inline.group(1)), _money(inline.group(2))
            body = line[: inline.start()]
        lead = LEADING_QTY.match(body)
        if lead and not inline:
            qty = int(lead.group(1))
            unit = (amount / qty).quantize(Decimal("0.01"))
        if pending_qty and abs(pending_qty[0] * pending_qty[1] - amount) <= Decimal("0.02"):
            qty, unit = pending_qty
        pending_qty = None

        label = clean_label(body)
        if _letters(label) < 3:
            if pending_label:
                label = pending_label
            else:
                continue
        pending_label = None
        items.append(ParsedLine(label[:255], Decimal(qty), unit, amount))

    receipt.lines = items
    return receipt
