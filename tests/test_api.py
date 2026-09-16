"""Tests pytest sur l'API Marketplace simulee.

Lancer depuis l'hote (API demarree via docker compose) :

    pip install pytest requests
    pytest tests/ -v
"""

import os

import pytest
import requests

BASE_URL = os.environ.get("API_URL", "http://localhost:5000")
TOKEN = os.environ.get("API_TOKEN", "formation-token-2026")
AUTH = {"Authorization": f"Bearer {TOKEN}"}
TEST_DATE = "2026-04-07"


def test_health_no_auth():
    r = requests.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_orders_requires_auth():
    r = requests.get(f"{BASE_URL}/orders", params={"date": TEST_DATE}, timeout=10)
    assert r.status_code == 401


def test_orders_missing_date_returns_400():
    r = requests.get(f"{BASE_URL}/orders", headers=AUTH, timeout=10)
    assert r.status_code == 400


def test_orders_are_deterministic():
    """Meme date = meme resultat : c'est ce qui rend le pipeline rejouable."""
    r1 = requests.get(
        f"{BASE_URL}/orders", params={"date": TEST_DATE}, headers=AUTH, timeout=10
    )
    r2 = requests.get(
        f"{BASE_URL}/orders", params={"date": TEST_DATE}, headers=AUTH, timeout=10
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()


def test_orders_schema_and_commission():
    r = requests.get(
        f"{BASE_URL}/orders", params={"date": TEST_DATE}, headers=AUTH, timeout=10
    )
    orders = r.json()["orders"]
    assert len(orders) > 0
    required = {
        "order_id", "dt", "customer_id", "seller_id", "product_id",
        "quantity", "unit_price", "total", "commission", "status",
    }
    for o in orders:
        assert required <= set(o)
        assert o["dt"] == TEST_DATE
        assert o["commission"] == pytest.approx(o["total"] * 0.12, abs=0.01)


def test_orders_reference_existing_dims():
    """Chaque commande doit pointer vers un vendeur et un produit connus
    (sinon les FK du DWH casseront au chargement)."""
    orders = requests.get(
        f"{BASE_URL}/orders", params={"date": TEST_DATE}, headers=AUTH, timeout=10
    ).json()["orders"]
    sellers = {s["seller_id"] for s in requests.get(
        f"{BASE_URL}/sellers", headers=AUTH, timeout=10
    ).json()["sellers"]}
    products = {p["product_id"] for p in requests.get(
        f"{BASE_URL}/products", headers=AUTH, timeout=10
    ).json()["products"]}
    for o in orders:
        assert o["seller_id"] in sellers
        assert o["product_id"] in products


def test_sellers_limit():
    r = requests.get(
        f"{BASE_URL}/sellers", params={"limit": 10}, headers=AUTH, timeout=10
    )
    assert r.status_code == 200
    assert len(r.json()["sellers"]) == 10
