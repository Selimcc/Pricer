# Pricer

[![Backend CI](https://github.com/Selimcc/Pricer/actions/workflows/backend.yml/badge.svg)](https://github.com/Selimcc/Pricer/actions/workflows/backend.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Community-driven grocery price comparison. Scan a product, see where it is cheapest around you, and find out which store to do your whole shopping list in.

Prices come from the community (dated, geolocated observations with a photo), from supermarket receipts and from the [Open Prices](https://prices.openfoodfacts.org) open data. Stores are real ones imported from OpenStreetMap. The app targets French supermarkets, so its interface is in French.

## Highlights

- **FastAPI + PostgreSQL/PostGIS.** "Around me" queries use `ST_DWithin` with a GiST index; stores are imported from OpenStreetMap once per area and kept in the database.
- **One receipt photo, every price of your shopping trip.** Local OCR with Tesseract, a French receipt parser (quantities, items sold by weight, loyalty discounts, coupons), then line-to-product matching backed by a per-retailer collective memory: once someone confirms that `THON NAT 3X80G` is a given product, everyone's next receipts fill in by themselves.
- **Trust, not just prices.** Each price carries a confidence score (freshness with a 7-day half-life, Bayesian-averaged votes, photo and on-site GPS proof). Observations more than 5 km from the store are refused, outliers are flagged, contributions are rate limited, barcodes are validated by their check digit.
- **Open data first, own data over time.** Nightly import of the full Open Prices export for a region, product sheets from Open Food Facts and its sister databases queried in parallel, and a provider interface so a new price source is one class.
- **Shopping list optimisation.** Estimated total per store, missing products, multi-store split when it is worth it, and equivalent private-label products substituted across retailers.
- **Production habits on a side project.** Alembic migrations (including an automatic upgrade path from the v0.2 schema), 53 tests against a real PostGIS database and a real OCR run, ruff, GitHub Actions for the backend and the mobile typecheck, Docker Compose, nightly backups and a named Cloudflare tunnel for a home server.

## Features

- Barcode scanner with product suggestions; unknown products can be created with a packaging photo
- Price comparison around you: one price per store (latest valid observation), unit price per kilo or litre, "good deal" badge
- Price observation with store choice, typed promotion and proof photo; "still this price / it changed" votes, a disputed price falls back to the previous one
- 90-day price history chart (regular vs promotional prices, usual price)
- Receipt capture and review: confirm, scan the item, search or skip each line, then publish
- Shopping list with a "where to shop" comparison
- Contributor profile with level and confirmations received
- Admin dashboard on the server (`/dashboard`) and OpenAPI docs (`/docs`)

## Architecture

```text
Phone (Expo / React Native)
        │ HTTPS (local Wi-Fi, or a Cloudflare tunnel with an API key)
        ▼
FastAPI ──► PostgreSQL + PostGIS
   │
   ├──► Open Food Facts & sister databases   (product sheets)
   ├──► Open Prices                          (public prices, nightly import)
   └──► Overpass / OpenStreetMap             (stores)

worker:  nightly Open Prices import and product enrichment
backup:  nightly pg_dump, 14 days kept
```

The phone never talks to PostgreSQL directly, and PostgreSQL is only exposed on the host (127.0.0.1).

**Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 + PostGIS, Tesseract, Docker Compose, Expo / React Native, TypeScript, react-native-svg, GitHub Actions.

## Run it locally

**Backend**

```bash
docker compose up --build -d
curl http://localhost:8000/health
```

On start-up, `python -m app.migrate` brings the database schema up to date, then adds demo data (`SEED_DEMO=false` to skip it).

**Mobile**

```bash
cd mobile
npm install
cp .env.example .env      # set the PC's Wi-Fi IP address
npx expo start
```

Scan the QR code with Expo Go; the phone and the PC must be on the same Wi-Fi. To test without moving, set `EXPO_PUBLIC_DEMO_LOCATION=true` in `mobile/.env` and scan `3017620422003`.

**Using it in a store (4G)**

1. Copy `.env.example` to `.env` and put a long secret in `APP_API_KEY`; put the same value in `mobile/.env` as `EXPO_PUBLIC_API_KEY`.
2. Start the free Cloudflare tunnel: `docker compose --profile tunnel up -d`, then read the `https://….trycloudflare.com` address in `docker compose logs tunnel`.
3. In the app, **Moi → Serveur → Modifier**, paste the address, then test and save.

Requests coming through the tunnel must carry `X-Pricer-Key`, otherwise the API answers 401; the local network is unchanged. For a permanent address on your own domain, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql+psycopg://grocery:grocery_dev_password@localhost:5432/grocery_test pytest
```

The test database needs PostGIS and is emptied on every run. The receipt tests need `tesseract-ocr` and `tesseract-ocr-fra`.

## Main endpoints

| | |
|---|---|
| `GET /products/{ean}` | product sheet (our database, then Open Food Facts) |
| `POST /products` · `POST /products/{ean}/image` | add an unknown product, add a packaging photo |
| `GET /products/{ean}/comparison` · `GET /products/{ean}/history` | current prices around a point, price history |
| `GET /stores/nearby` · `GET /stores/{id}` | nearby stores, latest prices in a store |
| `POST /observations` · `POST /observations/{id}/proof` · `POST /observations/{id}/vote` | report, prove, vote |
| `GET/POST/PATCH/DELETE /users/{id}/list` · `GET /users/{id}/list/comparison` | shopping list and store comparison |
| `GET /users/{id}/contributions` | contributor profile |
| `POST /receipts` · `GET /receipts/{id}` · `PATCH /receipts/{id}/lines/{line}` · `POST /receipts/{id}/publish` | receipt upload, review and publishing |

Configuration lives in `backend/app/core/config.py` (environment variables such as `SEED_DEMO`, `IMPORT_BBOX`, `PRICE_MAX_AGE_DAYS`, `GPS_MAX_DISTANCE_KM`, `MAX_CONTRIBUTIONS_PER_HOUR`).

## Known limitations

- Anonymous identity per device, no accounts yet, so votes cannot be weighted by reputation.
- Items sold by weight are read from receipts but not published yet: they need per-category prices per kilo.
- Overpass is a free public service and can be slow or rate limited.

## Roadmap

- Accounts and reputation to weight votes
- Per-kilo prices for fresh produce, to publish weighted receipt items
- Store map in the app
- TestFlight build with EAS Update once more people test it

## Data

Open Prices and store data © OpenStreetMap and Open Food Facts contributors, under the ODbL. Community data is kept separate from ODbL data through each price's `source` field.

## License

Code under the [MIT](LICENSE) license © 2026 Selim Jabnoun.
