# Pricer sur le PC de bureau (serveur maison)

Objectif : l'API tourne en permanence sur le PC de bureau, joignable depuis le téléphone partout (4G) à une adresse fixe `https://api.ton-domaine.fr`, avec des prix réels dès le départ.

```text
iPhone (4G / Wi-Fi) ──► https://api.ton-domaine.fr ──► Cloudflare ──► tunnel ──► PC de bureau
                                                                                  ├─ api      (FastAPI)
                                                                                  ├─ db       (PostgreSQL + PostGIS)
                                                                                  ├─ worker   (imports de nuit)
                                                                                  └─ backup   (sauvegarde chaque nuit)
```

Aucun port à ouvrir sur la box : le tunnel sort du PC vers Cloudflare.

## 1. Préparer le PC (Windows)

1. Installer Git et Docker Desktop (comme sur le portable).
2. Docker Desktop > Settings > General : cocher **Start Docker Desktop when you sign in to your computer**.
3. Paramètres Windows > Système > Alimentation : mise en veille **Jamais** (sur secteur). L'écran peut s'éteindre, pas le PC.
4. Après un redémarrage (mises à jour Windows), il faut rouvrir ta session pour que Docker reparte. Les conteneurs redémarrent alors tout seuls.

```powershell
cd $HOME\Desktop
git clone https://github.com/Selimcc/Pricer.git
cd Pricer
copy .env.example .env      # puis reprendre APP_API_KEY du portable (même valeur que mobile/.env)
docker compose up -d --build
docker compose logs -f worker   # le premier import Open Prices démarre tout de suite
```

Pour un rendu réel, sans les magasins fictifs de Paris : dans `.env`, `SEED_DEMO=false`, puis

```powershell
docker compose up -d
docker compose exec api python -m app.jobs.purge --demo
```

### Reprendre la base du portable (facultatif)

Sur le portable :

```powershell
cmd /c "docker compose exec -T db pg_dump -U grocery grocery > pricer.sql"
```

(`cmd /c` évite que PowerShell réencode le fichier.)

Copier `pricer.sql` sur le PC de bureau, puis, avant le premier `docker compose up -d` complet :

```powershell
docker compose up -d db
cmd /c "docker compose exec -T db psql -U grocery -d grocery < pricer.sql"
docker compose up -d --build
```

## 2. Passer le DNS du domaine chez Cloudflare (le site reste en ligne)

Cloudflare doit gérer le DNS du domaine pour créer `api.ton-domaine.fr`. Le domaine reste enregistré chez OVH (renouvellement, facture) ; seul l'annuaire DNS change de main. C'est gratuit.

1. Chez OVH, noter la **zone DNS** actuelle : Web Cloud > Noms de domaine > ton domaine > onglet *Zone DNS*.
2. Toujours chez OVH, onglet *DNSSEC* : **le désactiver** s'il est actif, et attendre la confirmation. Sinon le domaine (et le site) deviennent injoignables au changement.
3. Créer un compte Cloudflare, *Add a domain*, plan **Free**. Cloudflare importe les enregistrements existants.
4. Comparer avec la zone OVH notée en 1 : chaque enregistrement A, AAAA, CNAME, MX et TXT doit être là. Ajouter ceux qui manquent.
5. Pour les enregistrements du site existant, mettre le nuage en **gris (DNS only)** : le site fonctionne exactement comme avant.
6. Chez OVH, onglet *Serveurs DNS* > *Modifier les serveurs DNS* : remplacer par les deux serveurs indiqués par Cloudflare.
7. Attendre le mail de Cloudflare « domaine actif » (de quelques minutes à 24 h). Vérifier que le site s'affiche toujours.

## 3. Tunnel nommé : l'adresse fixe

1. Cloudflare > **Zero Trust** > Networks > **Tunnels** > *Create a tunnel* > type *Cloudflared*, nom `pricer`.
2. Choisir l'environnement **Docker** et copier le jeton (la longue chaîne après `--token`). Ne pas lancer leur commande.
3. Ajouter une route publique (*Public hostname*) : sous-domaine `api`, ton domaine, service `HTTP` → `api:8000`.
4. Dans `.env` : `CLOUDFLARE_TUNNEL_TOKEN=<le jeton>`, puis :

```powershell
docker compose --profile server up -d
docker compose stop tunnel          # l'ancien tunnel temporaire ne sert plus
curl.exe https://api.ton-domaine.fr/health
```

5. Dans l'app : onglet **Moi** > **Serveur** > **Modifier** > `https://api.ton-domaine.fr` > *Tester et enregistrer*. Mettre aussi cette adresse dans `mobile/.env` (`EXPO_PUBLIC_API_URL`) pour qu'elle soit celle par défaut.

Le profil `server` ajoute aussi la sauvegarde : un fichier `backups/pricer-AAAA-MM-JJ.sql.gz` par nuit, 14 jours gardés.

## 4. Les prix

**Open Prices (automatique)** : le worker importe chaque nuit tous les prix récents de la zone `IMPORT_BBOX` (Île-de-France par défaut). Relance à la main :

```powershell
docker compose exec api python -m app.jobs.open_prices_import
```

**Sites des enseignes (test personnel)** : d'abord le diagnostic, qui dit pour chaque enseigne si on arrive à lire ses prix depuis ton PC :

```powershell
docker compose exec api python -m app.jobs.probe
```

Il enregistre les pages reçues dans `data/probe/`. Envoie-moi le résumé affiché et le dossier `data/probe` zippé : j'ajuste les lecteurs enseigne par enseigne. Résultat du 7 octobre 2026 : Carrefour et Monoprix refusent, e.leclerc et Franprix n'ont pas de pages exploitables, Auchan répond. Dans `.env` : `ENABLE_ONLINE_PRICES=true` et `ONLINE_RETAILERS=auchan`, puis :

```powershell
docker compose up -d
docker compose exec api python -m app.jobs.online index        # ~300 000 pages Auchan, quelques minutes
docker compose exec api python -m app.jobs.online lookup 3274080005003
docker compose exec api python -m app.jobs.online status
```

À chaque fiche produit ouverte, l'API cherche le prix sur les sites (une page à la fois par site, robots.txt respecté, pause de 24 h pour un site qui bloque) et l'affiche dans les magasins de l'enseigne autour de toi, avec la mention « Prix carrefour.fr », « Prix e.leclerc »… Les produits de ta liste sont remis à jour chaque nuit.

**Avant de faire tester l'app à d'autres personnes :**

```powershell
docker compose exec api python -m app.jobs.purge --online
```

et `ENABLE_ONLINE_PRICES=false`. Ces prix ne doivent pas sortir de ton usage personnel.

## 5. L'app sur l'iPhone sans le portable

Expo Go charge le code de l'app depuis Metro (`npx expo start`). Hors du Wi-Fi, il faut que Metro soit joignable :

- **Gratuit** : lancer Metro sur le PC de bureau en mode tunnel, `cd mobile` puis `npx expo start --tunnel`. À la maison, ngrok devrait passer (c'est le réseau de l'école qui bloquait). Le projet reste dans « Récemment ouverts » d'Expo Go. Il faut relancer la commande si le PC redémarre.
- **99 $/an (compte Apple Developer)** : une vraie app installée via TestFlight, mise à jour avec EAS Update, sans Metro ni PC allumé pour l'app (l'API reste sur le PC). À envisager quand d'autres personnes testeront.

## Commandes utiles

```powershell
docker compose ps                         # ce qui tourne
docker compose logs -f api worker         # journaux
docker compose exec api python -m app.jobs.online status
git pull ; docker compose up -d --build   # mettre à jour le serveur
```
