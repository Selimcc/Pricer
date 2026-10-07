# Pricer — prix alimentaires communautaires (V0.6)

Scanner un produit, voir où il est le moins cher autour de soi, et savoir dans quel magasin faire sa liste de courses.
Les prix viennent de la communauté (relevés datés, géolocalisés, avec photo) et d'Open Prices ; les magasins réels viennent d'OpenStreetMap.

> Nom de travail : « Pricer ». « Waze » est une marque de Google et ne peut pas être utilisé publiquement.

## Stratégie données

Phase actuelle : on s'appuie sur les bases ouvertes pour démarrer (Open Food Facts et ses bases sœurs pour les fiches, Open Prices pour les prix), mais tout ce qui passe par l'app est gardé chez nous.

- **Catalogue** : notre base d'abord, puis Open Food Facts (alimentation), Open Beauty Facts (hygiène, beauté), Open Pet Food Facts (animaux) et Open Products Facts (maison, entretien, le reste), interrogées en parallèle. Un produit inconnu partout est créé par l'utilisateur, avec photo. Une fiche sans photo peut être complétée par la communauté.
- **Prix** : chaque prix garde sa source (`community`, `open_prices`, `demo`). Les données communautaires restent séparables des données ODbL.
- **Tickets de caisse** : une photo de ticket = tous les prix des courses. Chaque association « libellé du ticket → produit » validée par un utilisateur est mémorisée par enseigne : les tickets suivants de tout le monde se remplissent tout seuls. Cette mémoire collective est 100 % à nous.
- **Objectif** : que notre base devienne la référence et que les sources externes ne servent plus qu'au premier scan.

## Prix réels dès le départ (V0.6)

- **Open Prices en entier** : chaque nuit, le service `worker` télécharge l'export complet d'Open Prices et importe tous les prix récents de la zone (`IMPORT_BBOX`, Île-de-France par défaut). Les magasins ont des prix avant le premier scan ; une fiche importée (nom seul) est complétée au premier scan.
- **Sites des enseignes, test personnel uniquement** (`ENABLE_ONLINE_PRICES=true`, désactivé par défaut) : à l'ouverture d'une fiche, l'API lit le prix du produit sur carrefour.fr, e.leclerc, auchan.fr, courses.monoprix.fr, franprix.fr dans la description produit des pages (schema.org), en vérifiant l'EAN. robots.txt respecté, une page à la fois par site, plafond quotidien, pause de 24 h pour un site qui bloque : on ne contourne aucune protection. Le prix est affiché dans les magasins de l'enseigne autour de l'utilisateur (« Prix carrefour.fr »). Source `online`, masquée dès que l'option est coupée, supprimée par `python -m app.jobs.purge --online`. Ces prix ne doivent jamais faire partie d'une version publique (conditions d'utilisation des sites, droit des bases de données).
- **Serveur maison** : PC de bureau + tunnel Cloudflare nommé sur un domaine (adresse fixe), sauvegarde nocturne. Voir [DEPLOIEMENT.md](DEPLOIEMENT.md).

## Tickets de caisse (V0.5)

1. L'utilisateur photographie son ticket. L'API le lit avec Tesseract (gratuit, local, inclus dans l'image Docker).
2. Le texte est analysé : enseigne, date, total, articles, quantités (« 2 x 1,29 »), articles au poids, remises fidélité et bons de réduction.
3. Le magasin est déduit de l'enseigne lue et de la position GPS.
4. Chaque ligne est rapprochée d'un produit : mémoire collective d'abord, puis ressemblance avec le catalogue (abréviations gérées). L'utilisateur confirme, scanne l'article ou l'ignore.
5. À la publication, chaque ligne devient un relevé de prix (source « Ticket de caisse », prix après remise, date d'achat réelle).

La photo du ticket est stockée dans un volume privé (`receipts`), jamais servie par l'API : elle compte comme preuve mais n'est montrée à personne. Les articles au poids (fruits, légumes) sont lus mais pas encore publiés : il faudra des prix par catégorie au kilo.

## Ce qui change dans la V0.4

**Vraies données**
- Les supermarchés et supérettes autour de l'utilisateur sont importés automatiquement depuis OpenStreetMap (une fois par zone, puis gardés en base).
- Les prix réels d'Open Prices (Open Food Facts) sont récupérés pour chaque produit consulté, avec leurs photos de preuve.
- Architecture « provider » : ajouter une source de prix = écrire une classe dans `backend/app/services/providers/`.

**Produit**
- Liste de courses avec comparaison des magasins : total estimé par magasin, produits manquants, option « plusieurs magasins ».
- Un seul prix par magasin dans la comparaison (le relevé le plus récent encore valable), prix au kilo/litre, « bon plan » quand le prix est nettement sous le prix habituel.
- Votes « c'est toujours ce prix » / « il a changé » ; un prix massivement contesté disparaît au profit du précédent.
- Photo de l'étiquette comme preuve, stockée localement (prête pour S3).
- Ajout d'un produit absent d'Open Food Facts.
- Profil : contributions, niveau, confirmations reçues.
- Graphique d'évolution du prix sur 90 jours dans la fiche produit (prix normaux / promos, prix habituel).

**Fiabilité**
- Score de confiance v2 : fraîcheur (demi-vie 7 jours), votes (moyenne bayésienne), preuves (photo, GPS vérifié sur place).
- Contrôle de présence : refus au-delà de 5 km du magasin, « relevé sur place » sous 500 m.
- Prix anormal (très loin de la médiane) accepté mais signalé ; correction au lieu de doublon ; limite de 40 relevés/heure.
- Validation de la clé de contrôle des codes-barres (une lecture ratée n'envoie plus de faux produit).

**Technique**
- Migrations Alembic. Une base V0.2 existante est reconnue et migrée sans perte de données.
- PostGIS réellement utilisé (`ST_DWithin` + index GiST) pour les recherches « autour de moi ».
- API découpée en routers, tests (dont un OCR réel) sur une vraie base PostGIS, CI GitHub Actions (backend + typecheck mobile).
- App mobile découpée en écrans, nouvelle interface, navigation par onglets, identifiant anonyme persistant.

## Architecture

```text
Téléphone (Expo / React Native)
        │ HTTP (Wi-Fi local)
        ▼
FastAPI ──► PostgreSQL + PostGIS
   │
   ├──► Open Food Facts (fiche produit)
   ├──► Open Prices     (prix publics)
   └──► Overpass / OSM  (magasins)

PC : http://localhost:8000/dashboard   ·   http://localhost:8000/docs
```

Le téléphone ne parle jamais directement à PostgreSQL. PostgreSQL n'est exposé que sur la machine (127.0.0.1).

## Démarrer

### 1. Backend

```bash
docker compose up --build -d
curl http://localhost:8000/health
```

Au démarrage, `python -m app.migrate` met la base à jour (ta base V0.2 est conservée) puis ajoute les données de démo.

### 2. Mobile

```bash
cd mobile
npm install
cp .env.example .env      # puis mettre l'IP Wi-Fi du PC (ipconfig)
npx expo start
```

Scanner le QR code avec Expo Go. Le téléphone et le PC doivent être sur le même Wi-Fi.

### Utiliser l'app en magasin (4G)

Par défaut, le téléphone doit être sur le même Wi-Fi que le PC. Pour l'utiliser dehors :

1. À la racine, copie `.env.example` en `.env` et mets une longue clé secrète dans `APP_API_KEY`.
2. Mets la même valeur dans `mobile/.env` : `EXPO_PUBLIC_API_KEY=...`
3. Lance le tunnel Cloudflare (gratuit, sans compte) :

   ```bash
   docker compose --profile tunnel up -d
   docker compose logs tunnel        # repère l'adresse https://xxx-yyy.trycloudflare.com
   ```

4. Dans l'app, onglet **Moi** > **Serveur** > **Modifier** : colle l'adresse du tunnel, puis « Tester et enregistrer ».
5. Lance Expo en mode tunnel pour que le téléphone charge l'app hors du Wi-Fi : `npx expo start --tunnel`.

Les requêtes qui passent par le tunnel doivent porter la clé (`X-Pricer-Key`), sinon l'API répond 401. Sur le réseau local, rien ne change. L'adresse du tunnel change à chaque redémarrage du conteneur `tunnel` ; le PC doit rester allumé.

### Parcours de test

1. Autoriser caméra et localisation : l'onglet **Magasins** doit lister les vrais magasins autour de toi (la première fois, l'import OSM prend quelques secondes).
2. Scanner un produit de ton placard : prix Open Prices éventuels + magasins proches.
3. En magasin : **Relever un prix**, choisir le magasin (badge « Tu es ici »), photographier l'étiquette, publier.
4. **Ma liste** : scanner plusieurs produits, regarder « Où faire tes courses ».
5. Vérifier sur le dashboard PC que le relevé apparaît.

Pour tester sans te déplacer : `EXPO_PUBLIC_DEMO_LOCATION=true` dans `mobile/.env` (ou l'interrupteur dans l'onglet **Moi**) et le code `3017620422003`.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql+psycopg://grocery:grocery_dev_password@localhost:5432/grocery_test pytest
```

La base de test doit avoir PostGIS ; elle est vidée à chaque lancement.

## Endpoints principaux

| | |
|---|---|
| `GET /products/{ean}` | fiche produit (base, puis Open Food Facts) |
| `POST /products` | ajouter un produit inconnu |
| `POST /products/{ean}/image` | photo d'emballage pour un produit qui n'en a pas |
| `GET /products/{ean}/comparison` | prix actuels autour d'un point |
| `GET /products/{ean}/history` | historique des relevés |
| `GET /stores/nearby` · `GET /stores/{id}` | magasins proches, derniers prix d'un magasin |
| `POST /observations` · `POST /observations/{id}/proof` · `POST /observations/{id}/vote` | relever, prouver, voter |
| `GET/POST/PATCH/DELETE /users/{id}/list` · `GET /users/{id}/list/comparison` | liste de courses |
| `GET /users/{id}/contributions` | profil contributeur |
| `POST /receipts` · `GET /receipts` · `GET/PATCH /receipts/{id}` | ticket : photo, lecture, liste, correction |
| `PATCH /receipts/{id}/lines/{line}` · `POST /receipts/{id}/publish` | associer une ligne, publier les prix |

## Configuration (variables d'environnement du backend)

`SEED_DEMO`, `ENABLE_OPENFOODFACTS`, `ENABLE_OPEN_PRICES`, `ENABLE_OSM_IMPORT`, `UPLOAD_DIR`, `GPS_MAX_DISTANCE_KM`, `GPS_VERIFIED_RADIUS_M`, `MAX_CONTRIBUTIONS_PER_HOUR` : voir `backend/app/core/config.py`.

## Limites connues

- Identité anonyme par appareil, pas encore de comptes : n'importe qui peut voter avec un nouvel identifiant.
- Mot de passe PostgreSQL et CORS adaptés au développement local uniquement.
- Les photos sont stockées sur le disque du conteneur (volume `uploads`).
- Overpass (OSM) est un service public gratuit : il peut être lent ou refuser des requêtes en cas d'abus.

## Tâches (dans le conteneur de l'API)

```bash
docker compose exec api python -m app.jobs.open_prices_import   # import Open Prices de la zone
docker compose exec api python -m app.jobs.probe                # diagnostic des sites des enseignes
docker compose exec api python -m app.jobs.online status        # prix en ligne : état par enseigne
docker compose exec api python -m app.jobs.online lookup <EAN>  # tester un produit
docker compose exec api python -m app.jobs.purge --online       # supprimer les prix en ligne
docker compose exec api python -m app.jobs.purge --demo         # supprimer la démo (SEED_DEMO=false)
```

## Suite proposée

1. Ajuster les lecteurs des enseignes d'après le diagnostic (`probe`) lancé depuis le PC de bureau.
2. Prix au kilo par catégorie (fruits, légumes, rayon trad) pour publier les articles au poids des tickets.
3. Comptes et réputation, pour pondérer les votes.
4. Carte des magasins dans l'app.
5. App installable (TestFlight + EAS Update) quand d'autres personnes testeront ; AWS seulement une fois l'usage validé.

Données : prix Open Prices et magasins © contributeurs OpenStreetMap, sous licence ODbL ; fiches produits Open Food Facts.
