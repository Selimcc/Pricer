"""Tâches lancées hors des requêtes HTTP : imports, diagnostics, ménage.

Toutes s'exécutent dans le conteneur de l'API :
    docker compose exec api python -m app.jobs.<tâche> --help
"""
