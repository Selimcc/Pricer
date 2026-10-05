import httpx


async def lookup_ean(ean: str):
    url = f"https://world.openfoodfacts.org/api/v2/product/{ean}.json"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers={"User-Agent": "GroceryWazePrototype/0.1"})
            response.raise_for_status()
            data = response.json()
    except Exception:
        return None

    if data.get("status") != 1:
        return None

    p = data.get("product", {})
    return {
        "name": p.get("product_name") or p.get("product_name_fr") or "Produit inconnu",
        "brand": p.get("brands"),
        "quantity": p.get("quantity"),
        "image_url": p.get("image_front_url") or p.get("image_url"),
    }
