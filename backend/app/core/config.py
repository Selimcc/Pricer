from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://grocery:grocery_dev_password@localhost:5432/grocery"
    cors_origins: str = "*"

    # Clé exigée pour les requêtes qui arrivent par Internet (tunnel Cloudflare).
    # Vide = pas de contrôle (réseau local uniquement).
    app_api_key: str = ""

    # Données de démonstration (magasins fictifs dans Paris centre)
    seed_demo: bool = True

    # Sources externes. Désactivables pour travailler hors ligne ou en test.
    enable_openfoodfacts: bool = True
    enable_open_prices: bool = True
    enable_osm_import: bool = True
    http_user_agent: str = "Pricer/0.6 (prototype; github.com/Selimcc/Pricer)"
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
    # Tickets de caisse : dossier privé, jamais servi par l'API
    receipts_dir: str = "/app/receipts"
    enable_ocr: bool = True
    ocr_languages: str = "fra"
    max_upload_mb: int = 8

    # Dossier de travail des tâches de fond (exports téléchargés, diagnostics)
    data_dir: str = "/app/data"

    # Import complet d'Open Prices (export quotidien) pour une zone.
    # Zone = « lat_min,lon_min,lat_max,lon_max » ; par défaut l'Île-de-France.
    open_prices_export_url: str = "https://prices.openfoodfacts.org/data/prices.jsonl.gz"
    import_bbox: str = "48.12,1.44,49.24,3.56"
    open_prices_import_days: int = 365

    # Prix des sites des enseignes (phase de test, usage personnel).
    # Désactivé par défaut : ces prix ne doivent jamais apparaître dans une version publique.
    enable_online_prices: bool = False
    online_retailers: str = ""  # aucune lecture automatique : les sites testés bloquent ou cachent leurs prix
    online_user_agent: str = "Pricer/0.6 (test personnel, non commercial)"
    online_min_delay_s: float = 4.0          # entre deux pages d'un même site
    online_cache_hours: int = 24             # un prix trouvé n'est pas redemandé avant
    online_miss_cache_days: int = 7          # produit absent du site : on ne redemande pas avant
    online_wait_s: float = 8.0               # attente max pendant l'affichage d'une fiche produit
    online_daily_cap: int = 400              # pages max par site et par jour
    online_block_hours: int = 24             # un site qui bloque est laissé tranquille

    # Tâches planifiées (service « worker ») : heure UTC de la tournée de nuit (2 h UTC = 4 h à Paris l'été)
    worker_hour_utc: int = 2


settings = Settings()
