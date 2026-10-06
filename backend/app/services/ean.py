"""Validation et normalisation des codes-barres (EAN-13, EAN-8, UPC-A, UPC-E).

Le dernier chiffre d'un code-barres est une clé de contrôle. La vérifier
permet de rejeter une lecture ratée au lieu de chercher un faux produit.
"""


def _digits(code: str) -> str:
    return "".join(c for c in (code or "") if c.isdigit())


def _check_digit(body: str) -> int:
    # Poids 3 / 1 en partant de la droite (règle GS1 commune EAN/UPC)
    total = 0
    for i, ch in enumerate(reversed(body)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10


def has_valid_checksum(code: str) -> bool:
    if len(code) not in (8, 12, 13, 14) or not code.isdigit():
        return False
    return _check_digit(code[:-1]) == int(code[-1])


def expand_upc_e(code: str) -> str | None:
    """UPC-E (8 chiffres) -> UPC-A (12 chiffres), ou None si invalide."""
    if len(code) != 8 or code[0] not in "01":
        return None
    ns, d, check = code[0], code[1:7], code[7]
    last = d[5]
    if last in "012":
        body = d[0:2] + last + "0000" + d[2:5]
    elif last == "3":
        body = d[0:3] + "00000" + d[3:5]
    elif last == "4":
        body = d[0:4] + "00000" + d[4]
    else:
        body = d[0:5] + "0000" + last
    upc_a = ns + body + check
    return upc_a if has_valid_checksum(upc_a) else None


def normalize_ean(raw: str) -> str | None:
    """Retourne un code normalisé (EAN-13 ou EAN-8) ou None si la lecture est invalide.

    - UPC-A (12) devient EAN-13 avec un 0 devant (convention Open Food Facts)
    - UPC-E (8, commençant par 0/1) est développé si la clé EAN-8 ne colle pas
    """
    code = _digits(raw)
    if len(code) == 13 and has_valid_checksum(code):
        return code
    if len(code) == 12 and has_valid_checksum(code):
        return "0" + code
    if len(code) == 14 and has_valid_checksum(code) and code.startswith("0"):
        return code[1:]
    if len(code) == 8:
        if has_valid_checksum(code):
            return code
        upc_a = expand_upc_e(code)
        if upc_a:
            return "0" + upc_a
    return None
