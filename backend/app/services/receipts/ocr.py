"""Lecture du texte d'une photo de ticket (Tesseract, gratuit et local).

L'interface `extract_text` est volontairement simple : on pourra brancher
plus tard un autre moteur (modèle de vision, service cloud) sans toucher
au reste du pipeline.
"""
import io

from app.core.config import settings


class OcrUnavailable(RuntimeError):
    pass


def _prepare(image_bytes: bytes):
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)  # photo de téléphone : remettre à l'endroit
    img = ImageOps.grayscale(img)
    # Les tickets sont étroits : on vise ~1600 px de large pour des caractères lisibles
    if img.width < 1400:
        ratio = 1600 / img.width
        img = img.resize((1600, int(img.height * ratio)))
    elif img.width > 2400:
        ratio = 2000 / img.width
        img = img.resize((2000, int(img.height * ratio)))
    return ImageOps.autocontrast(img, cutoff=2)


def extract_text(image_bytes: bytes) -> str:
    if not settings.enable_ocr:
        raise OcrUnavailable("La lecture des tickets est désactivée sur ce serveur.")
    try:
        import pytesseract
    except ImportError as exc:
        raise OcrUnavailable("Moteur de lecture absent (pytesseract).") from exc
    try:
        image = _prepare(image_bytes)
        # psm 4 : une colonne de texte de tailles variables, le cas d'un ticket
        return pytesseract.image_to_string(image, lang=settings.ocr_languages, config="--psm 4")
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailable("Tesseract n'est pas installé dans le conteneur.") from exc
