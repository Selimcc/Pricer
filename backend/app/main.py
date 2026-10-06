from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers import observations, products, stores, system, users
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

for router in (system.router, products.router, stores.router, observations.router, users.router):
    app.include_router(router)

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
