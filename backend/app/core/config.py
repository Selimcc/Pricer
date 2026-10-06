from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://grocery:grocery_dev_password@localhost:5432/grocery"
    cors_origins: str = "*"

    # Données de démonstration (magasins fictifs dans Paris centre)
    seed_demo: bool = True

    # Sources externes. Désactivables pour travailler hors ligne ou en test.
    enable_openfoodfacts: bool = True
    enable_open_prices: bool = True
    enable_osm_import: bool = True
    http_user_agent: str = "Pricer/0.4 (prototype; github.com/Selimcc/Pricer)"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    open_prices_url: str = "https://prices.openfoodfacts.org/api/v1"

    # Fenêtres de temps
    open_prices_sync_hours: int = 12
    osm_area_refresh_days: int = 30
    price_max_age_days: int = 120

    # Contribution
    gps_verified_radius_m: float = 500.0
    gps_max_distance_km: float = 5.0
    max_contributions_per_hour: int = 40

    # Stockage des preuves photo (dossier local, remplaçable par S3 plus tard)
    upload_dir: str = "/app/uploads"
    max_upload_mb: int = 8


settings = Settings()
