import hmac
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers import observations, products, receipts, stores, system, users
from app.routers.system import API_VERSION

app = FastAPI(
    title="Pricer API",
    version=API_VERSION,
    description=(
        "Prix alimentaires communautaires, géolocalisés et vérifiables. "
        "Sources : relevés de la communauté, Open Prices (ODbL), magasins OpenStreetMap (ODbL)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_origins == "*" else settings.cors_origins.split(","),
    allow_credentials=settings.cors_origins != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Requêtes venues d'Internet : Cloudflare ajoute toujours l'en-tête Cf-Connecting-Ip.
# Sur le réseau local (Wi-Fi, dashboard du PC), pas de clé nécessaire.
PUBLIC_PATHS = ("/health",)
PUBLIC_PREFIXES = ("/uploads/",)


@app.middleware("http")
async def require_key_from_internet(request: Request, call_next):
    if (
        settings.app_api_key
        and "cf-connecting-ip" in request.headers
        and request.method != "OPTIONS"
        and request.url.path not in PUBLIC_PATHS
        and not request.url.path.startswith(PUBLIC_PREFIXES)
    ):
        given = request.headers.get("x-pricer-key", "")
        if not hmac.compare_digest(given.encode(), settings.app_api_key.encode()):
            return JSONResponse(
                status_code=401,
                content={"detail": {"code": "api_key_required",
                                    "message": "Clé d'accès manquante ou invalide (EXPO_PUBLIC_API_KEY)."}},
            )
    return await call_next(request)


for router in (system.router, products.router, stores.router, observations.router, receipts.router, users.router):
    app.include_router(router)

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
