# Running Pricer on a home server

Goal: the API runs permanently on a desktop PC and is reachable from the phone anywhere (4G) at a fixed address such as `https://api.your-domain.com`, with real prices from day one.

```text
Phone (4G / Wi-Fi) ──► https://api.your-domain.com ──► Cloudflare ──► tunnel ──► desktop PC
                                                                                   ├─ api      (FastAPI)
                                                                                   ├─ db       (PostgreSQL + PostGIS)
                                                                                   ├─ worker   (nightly imports)
                                                                                   └─ backup   (nightly dump)
```

No port needs to be opened on the router: the tunnel goes out from the PC to Cloudflare.

## 1. Prepare the PC (Windows)

1. Install Git and Docker Desktop.
2. Docker Desktop → Settings → General: tick **Start Docker Desktop when you sign in to your computer**.
3. Windows Settings → System → Power: sleep **Never** when plugged in. The screen may turn off, the PC may not.
4. After a reboot (Windows updates), sign in again so that Docker starts; the containers then restart on their own.

```powershell
git clone https://github.com/Selimcc/Pricer.git
cd Pricer
copy .env.example .env      # set APP_API_KEY (same value as mobile/.env)
docker compose up -d --build
docker compose logs -f worker   # the first Open Prices import starts right away
```

To run without the demo stores: set `SEED_DEMO=false` in `.env`, then

```powershell
docker compose up -d
docker compose exec api python -m app.jobs.purge --demo
```

### Moving an existing database (optional)

On the old machine:

```powershell
cmd /c "docker compose exec -T db pg_dump -U grocery grocery > pricer.sql"
```

(`cmd /c` prevents PowerShell from re-encoding the file.) Copy `pricer.sql` to the server, then before the first full `docker compose up -d`:

```powershell
docker compose up -d db
cmd /c "docker compose exec -T db psql -U grocery -d grocery < pricer.sql"
docker compose up -d --build
```

## 2. Move the domain's DNS to Cloudflare

Cloudflare must manage the domain's DNS to create `api.your-domain.com`. The domain stays with its registrar; only the DNS zone moves. It is free.

1. At the registrar, write down the current DNS zone.
2. Disable DNSSEC if it is active and wait for confirmation, otherwise the domain becomes unreachable during the switch.
3. Create a Cloudflare account, *Add a domain*, **Free** plan. Cloudflare imports the existing records.
4. Compare with the zone noted in step 1: every A, AAAA, CNAME, MX and TXT record must be there.
5. For an existing website's records, set the cloud to **grey (DNS only)** so the site behaves exactly as before.
6. At the registrar, replace the name servers with the two given by Cloudflare.
7. Wait for Cloudflare's "domain active" email (minutes to 24 h) and check that the website still loads.

## 3. Named tunnel: the fixed address

1. Cloudflare → **Zero Trust** → Networks → **Tunnels** → *Create a tunnel*, type *Cloudflared*, name `pricer`.
2. Choose **Docker** and copy the token (the long string after `--token`). Do not run their command.
3. Add a public hostname: subdomain `api`, your domain, service `HTTP` → `api:8000`.
4. In `.env`: `CLOUDFLARE_TUNNEL_TOKEN=<token>`, then:

```powershell
docker compose --profile server up -d
docker compose stop tunnel          # the temporary quick tunnel is no longer needed
curl.exe https://api.your-domain.com/health
```

5. In the app: **Moi → Serveur → Modifier** → `https://api.your-domain.com` → test and save. Also put this address in `mobile/.env` (`EXPO_PUBLIC_API_URL`) to make it the default.

The `server` profile also enables backups: one `backups/pricer-YYYY-MM-DD.sql.gz` per night, 14 days kept.

## 4. Prices

The worker imports every recent price in the `IMPORT_BBOX` area (Ile-de-France by default) from the Open Prices export each night, then completes imported product sheets from Open Food Facts. To run the import by hand:

```powershell
docker compose exec api python -m app.jobs.open_prices_import
```

## 5. The app on the phone without the laptop

Expo Go loads the app's code from Metro (`npx expo start`). Away from the Wi-Fi, Metro must be reachable:

- **Free**: run Metro on the server in tunnel mode, `cd mobile` then `npx expo start --tunnel`. Re-run it after a reboot.
- **Apple Developer account**: a real app installed through TestFlight and updated with EAS Update, with no Metro needed (the API stays on the server).

## Useful commands

```powershell
docker compose ps                         # what is running
docker compose logs -f api worker         # logs
git pull ; docker compose up -d --build   # update the server
```
