# Grocery Waze — Local Prototype V0.2

Prototype local d'une application mobile de comparaison de prix communautaires.

## Ce qui est nouveau dans V0.2

### Mobile
- gros bouton **Scanner un produit** ;
- scan EAN-13 / EAN-8 / UPC avec cadre de scan dédié ;
- récupération automatique de la position du téléphone ;
- fiche produit plus lisible ;
- comparaison triée par prix ;
- mise en avant du **meilleur prix** ;
- distance + fraîcheur du relevé ;
- barre de fiabilité communautaire ;
- boutons **Confirmer** / **Signaler** ;
- parcours **J'ai trouvé ce prix en magasin** ;
- sélection des magasins proches ;
- ajout d'un prix + promotion ;
- validation de présence par distance GPS.

### PC
Un dashboard local est disponible sur :

`http://localhost:8000/dashboard`

Il affiche les compteurs produits / magasins / relevés / votes et les derniers relevés communautaires. Il utilise la même API que le téléphone.

## Architecture

```text
Phone (Expo / React Native)
        |
        | HTTP sur le réseau local
        v
FastAPI
   |
   +---- PostgreSQL + PostGIS
   |
   +---- Open Food Facts (résolution EAN)

PC: http://localhost:8000/dashboard
API: http://localhost:8000/docs
```

Le téléphone **ne se connecte jamais directement à PostgreSQL**.

## 1. Prérequis

Installer :

- Docker Desktop
- Node.js 20+
- Git
- Expo Go sur iPhone ou Android

Pour le test local, le téléphone et le PC doivent être sur le même Wi-Fi.

## 2. Démarrer le backend + PostgreSQL

Depuis le dossier du projet :

```bash
docker compose up --build -d
```

Vérifier :

```bash
curl http://localhost:8000/health
```

Résultat attendu :

```json
{"status":"ok","database":"ok"}
```

Ouvrir ensuite :

- Dashboard : `http://localhost:8000/dashboard`
- Swagger : `http://localhost:8000/docs`

La base est automatiquement remplie avec des produits, magasins et prix de démonstration.

## 3. Démarrer le mobile

```bash
cd mobile
npm install
npx expo start
```

Scanner le QR avec Expo Go.

Créer `mobile/.env` :

```env
EXPO_PUBLIC_API_URL=http://YOUR_PC_LAN_IP:8000
```

Exemple :

```env
EXPO_PUBLIC_API_URL=http://192.168.1.42:8000
```

Sous Windows :

```powershell
ipconfig
```

Prendre l'IPv4 de la carte Wi-Fi/Ethernet utilisée par le PC.

## 4. Parcours de test conseillé

1. Démarrer Docker.
2. Ouvrir `http://localhost:8000/dashboard` sur le PC.
3. Démarrer Expo.
4. Ouvrir l'application sur le téléphone.
5. Autoriser caméra + localisation.
6. Scanner le produit de démonstration : `3017620422003`.
7. Vérifier les prix Carrefour / Monoprix / Auchan.
8. Confirmer ou signaler un prix.
9. Appuyer sur **J'ai trouvé ce prix en magasin**.
10. Choisir un magasin proche et publier un nouveau prix.
11. Revenir sur le dashboard PC : le relevé doit apparaître.

## Endpoints principaux

- `GET /health`
- `GET /stats`
- `GET /observations/recent`
- `GET /stores`
- `GET /stores/nearby`
- `GET /products/{ean}`
- `GET /products/{ean}/comparison`
- `POST /observations`
- `POST /observations/{id}/vote`

## Limites actuelles

Cette version reste volontairement locale :

- pas d'authentification réelle ;
- pas encore de photo de preuve uploadée ;
- magasins et prix de démonstration ;
- pas encore de scraping réel des enseignes ;
- pas encore d'Open Prices complet ;
- mot de passe PostgreSQL et CORS adaptés uniquement au développement local ;
- ne pas exposer directement cette API sur Internet.

## Suite logique

1. photo de ticket / étiquette comme preuve ;
2. historique des prix ;
3. prix au kg / L / unité ;
4. Open Prices comme source communautaire ;
5. comptes utilisateurs + réputation ;
6. vraie carte des magasins ;
7. providers par enseigne ;
8. puis seulement déploiement cloud / AWS.
