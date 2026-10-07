"""Tournée de nuit (service « worker » de docker compose).

Chaque jour à WORKER_HOUR_UTC :
- import Open Prices de la zone (si ENABLE_OPEN_PRICES) ;
- mise à jour des prix en ligne des produits suivis (si ENABLE_ONLINE_PRICES).
Chaque lundi : indexation des sitemaps des enseignes (si ENABLE_ONLINE_PRICES).

Au premier démarrage, l'import Open Prices est lancé tout de suite.
L'état est gardé dans data/worker-state.json.
"""
import json
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.db import SessionLocal

STATE_FILE = Path(settings.data_dir) / "worker-state.json"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def task_open_prices() -> None:
    from app.jobs.open_prices_import import run
    run()


def task_online_refresh() -> None:
    from app.jobs.online import cmd_refresh
    db = SessionLocal()
    try:
        cmd_refresh(db)
    finally:
        db.close()


def task_online_index() -> None:
    from app.jobs.online import cmd_index
    db = SessionLocal()
    try:
        cmd_index(db, [])
    finally:
        db.close()


# (nom, fonction, actif ?, période : "daily" | "weekly")
TASKS = [
    ("open_prices_import", task_open_prices, lambda: settings.enable_open_prices, "daily"),
    ("online_index", task_online_index, lambda: settings.enable_online_prices, "weekly"),
    ("online_refresh", task_online_refresh, lambda: settings.enable_online_prices, "daily"),
]


def is_due(name: str, period: str, state: dict, now: datetime) -> bool:
    last = state.get(name)
    if last is None:
        return True  # jamais lancée : tout de suite
    if now.hour < settings.worker_hour_utc:
        return False
    today = now.date().isoformat()
    if period == "daily":
        return last < today
    week = now.strftime("%G-W%V")
    return datetime.fromisoformat(last).strftime("%G-W%V") != week and now.weekday() == 0


RETRY_AFTER_FAILURE = timedelta(hours=1)


def run_due(now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    state = load_state()
    ran = []
    for name, func, enabled, period in TASKS:
        if not enabled() or not is_due(name, period, state, now):
            continue
        failed = state.get(f"{name}_failed_at")
        if failed and now - datetime.fromisoformat(failed) < RETRY_AFTER_FAILURE:
            continue
        print(f"[worker] {now:%Y-%m-%d %H:%M} UTC : {name}", flush=True)
        try:
            func()
            state[name] = now.date().isoformat()
            state.pop(f"{name}_failed_at", None)
        except Exception:
            traceback.print_exc()
            state[f"{name}_failed_at"] = now.isoformat()  # nouvel essai dans une heure
        save_state(state)
        ran.append(name)
    return ran


def main() -> None:
    print(f"[worker] démarré, tournée chaque jour à {settings.worker_hour_utc} h UTC", flush=True)
    time.sleep(30)  # laisse l'API appliquer les migrations
    while True:
        run_due()
        time.sleep(300)


if __name__ == "__main__":
    main()
