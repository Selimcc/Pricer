"""Accès par Internet (tunnel Cloudflare) : clé obligatoire, réseau local inchangé."""
from app.core.config import settings

VIA_TUNNEL = {"Cf-Connecting-Ip": "203.0.113.7"}


def test_local_network_needs_no_key(client, monkeypatch):
    monkeypatch.setattr(settings, "app_api_key", "secret-123")
    assert client.get("/stats").status_code == 200


def test_tunnel_requires_key(client, monkeypatch):
    monkeypatch.setattr(settings, "app_api_key", "secret-123")
    r = client.get("/stats", headers=VIA_TUNNEL)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "api_key_required"
    assert client.get("/stats", headers={**VIA_TUNNEL, "X-Pricer-Key": "wrong"}).status_code == 401
    assert client.get("/stats", headers={**VIA_TUNNEL, "X-Pricer-Key": "secret-123"}).status_code == 200
    # Le healthcheck reste ouvert pour vérifier que le tunnel répond
    assert client.get("/health", headers=VIA_TUNNEL).status_code == 200


def test_no_key_configured_means_open(client, monkeypatch):
    monkeypatch.setattr(settings, "app_api_key", "")
    assert client.get("/stats", headers=VIA_TUNNEL).status_code == 200
