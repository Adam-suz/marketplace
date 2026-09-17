"""Setup Metabase automatise : admin, connexion PostgreSQL DWH, 2 dashboards.

Usage : python scripts/setup_metabase.py
Prerequis : stack demarre (docker compose up -d) + Metabase initialise.
"""

import sys

import requests

MB = "http://localhost:3000"
EMAIL = "admin@maelys.local"
PASSWORD = "Admin2026!"


def main() -> None:
    s = requests.Session()

    # --- 1. Setup initial : compte admin ---------------------------------
    props = s.get(f"{MB}/api/session/properties", timeout=15).json()
    token = props.get("setup-token")
    if token:
        r = s.post(
            f"{MB}/api/setup",
            json={
                "token": token,
                "user": {
                    "first_name": "Admin",
                    "last_name": "Maelys",
                    "email": EMAIL,
                    "password": PASSWORD,
                },
                "prefs": {"site_name": "Maelys Marketplace", "allow_tracking": False},
            },
            timeout=30,
        )
        r.raise_for_status()
        print("[1] compte admin cree :", EMAIL)
    else:
        print("[1] setup deja fait, login...")

    # --- 2. Login ---------------------------------------------------------
    r = s.post(
        f"{MB}/api/session",
        json={"username": EMAIL, "password": PASSWORD},
        timeout=15,
    )
    r.raise_for_status()
    s.headers["X-Metabase-Session"] = r.json()["id"]
    print("[2] session ok")

    # --- 3. Source de donnees PostgreSQL ---------------------------------
    db_id = None
    for db in s.get(f"{MB}/api/database", timeout=15).json().get("data", []):
        if db["name"] == "DWH Marketplace":
            db_id = db["id"]
    if db_id is None:
        r = s.post(
            f"{MB}/api/database",
            json={
                "name": "DWH Marketplace",
                "engine": "postgres",
                "details": {
                    "host": "postgres-dwh",
                    "port": 5432,
                    "dbname": "dwh",
                    "user": "dwh_user",
                    "password": "dwh_password",
                    "ssl": False,
                },
            },
            timeout=60,
        )
        if r.status_code not in (200, 201):
            print("[3] ERREUR connexion DB :", r.text[:500])
            sys.exit(1)
        db_id = r.json()["id"]
    print("[3] database DWH Marketplace : id =", db_id)

    def card(name, query, display):
        r = s.post(
            f"{MB}/api/card",
            json={
                "name": name,
                "display": display,
                "dataset_query": {
                    "type": "native",
                    "native": {"query": query},
                    "database": db_id,
                },
                "visualization_settings": {},
            },
            timeout=30,
        )
        r.raise_for_status()
        print("    +", name)
        return r.json()["id"]

    # --- 4. Questions -----------------------------------------------------
    print("[4] creation des questions")
    c_ca_day = card(
        "CA du jour",
        "SELECT total_revenue FROM analytics.daily_summary ORDER BY dt DESC LIMIT 1",
        "scalar",
    )
    c_ca_30 = card(
        "CA sur 30 jours",
        "SELECT dt, total_revenue FROM analytics.daily_summary ORDER BY dt",
        "line",
    )
    c_top5_day = card(
        "Top 5 vendeurs du jour",
        """SELECT ds.name AS vendeur, sd.revenue
FROM analytics.seller_daily sd
JOIN dwh.dim_seller ds ON ds.seller_id = sd.seller_id
WHERE sd.dt = (SELECT max(dt) FROM analytics.seller_daily)
ORDER BY sd.revenue DESC LIMIT 5""",
        "bar",
    )
    c_top10_month = card(
        "Top 10 vendeurs du mois",
        """SELECT ds.name AS vendeur, SUM(sd.revenue) AS ca
FROM analytics.seller_daily sd
JOIN dwh.dim_seller ds ON ds.seller_id = sd.seller_id
GROUP BY ds.name ORDER BY ca DESC LIMIT 10""",
        "bar",
    )
    c_top3_evol = card(
        "Evolution CA top 3 vendeurs",
        """WITH top3 AS (
  SELECT seller_id FROM analytics.seller_daily
  GROUP BY seller_id ORDER BY SUM(revenue) DESC LIMIT 3
)
SELECT sd.dt, ds.name AS vendeur, SUM(sd.revenue) AS ca
FROM analytics.seller_daily sd
JOIN dwh.dim_seller ds ON ds.seller_id = sd.seller_id
WHERE sd.seller_id IN (SELECT seller_id FROM top3)
GROUP BY sd.dt, ds.name ORDER BY sd.dt""",
        "line",
    )
    c_inactive = card(
        "Vendeurs inactifs (> 7 jours sans vente)",
        """SELECT ds.seller_id, ds.name, ds.city, MAX(sd.dt) AS derniere_vente
FROM dwh.dim_seller ds
LEFT JOIN analytics.seller_daily sd ON sd.seller_id = ds.seller_id
GROUP BY ds.seller_id, ds.name, ds.city
HAVING MAX(sd.dt) IS NULL
    OR MAX(sd.dt) < (SELECT max(dt) FROM analytics.seller_daily) - 7
ORDER BY derniere_vente NULLS FIRST""",
        "table",
    )
    c_commissions = card(
        "Commissions par jour (12%)",
        "SELECT dt, total_commission FROM analytics.daily_summary ORDER BY dt",
        "line",
    )
    c_cat = card(
        "CA par categorie",
        """SELECT category, SUM(revenue) AS ca
FROM analytics.category_daily GROUP BY category ORDER BY ca DESC""",
        "bar",
    )
    c_fraud_count = card(
        "Commandes a prix suspect (dernier jour)",
        """SELECT COUNT(*) FROM dwh.fact_orders f
JOIN dwh.dim_product p ON p.product_id = f.product_id
WHERE f.dt = (SELECT max(dt) FROM dwh.fact_orders)
  AND ABS(f.unit_price - p.price) / p.price > 0.15""",
        "scalar",
    )
    c_fraud_price = card(
        "Prix anormaux vs catalogue",
        """SELECT f.dt, f.order_id, s.name AS vendeur, p.name AS produit,
       f.unit_price, p.price AS prix_catalogue,
       ROUND(100.0 * (f.unit_price - p.price) / p.price, 1) AS ecart_pct
FROM dwh.fact_orders f
JOIN dwh.dim_product p ON p.product_id = f.product_id
JOIN dwh.dim_seller s ON s.seller_id = f.seller_id
WHERE ABS(f.unit_price - p.price) / p.price > 0.15
ORDER BY ABS(f.unit_price - p.price) / p.price DESC
LIMIT 50""",
        "table",
    )
    c_fraud_cancel = card(
        "Vendeurs a fort taux d'annulation (> 25%)",
        """SELECT f.seller_id, s.name AS vendeur, s.city,
       COUNT(*) AS commandes,
       ROUND(100.0 * COUNT(*) FILTER (WHERE f.status = 'cancelled')
             / COUNT(*), 1) AS taux_annulation_pct
FROM dwh.fact_orders f
JOIN dwh.dim_seller s ON s.seller_id = f.seller_id
GROUP BY f.seller_id, s.name, s.city
HAVING 100.0 * COUNT(*) FILTER (WHERE f.status = 'cancelled') / COUNT(*) > 25
ORDER BY taux_annulation_pct DESC""",
        "table",
    )

    # --- 5. Dashboards ----------------------------------------------------
    print("[5] creation des dashboards")

    def dashboard(name, cards):
        # creer le dashboard vide, puis rattacher les cards via PUT
        # (le param 'dashcards' du POST est ignore par Metabase v0.59)
        r = s.post(f"{MB}/api/dashboard", json={"name": name}, timeout=30)
        r.raise_for_status()
        did = r.json()["id"]
        dashcards = []
        for i, cid in enumerate(cards):
            w, h = (8, 6) if len(cards) > 1 else (12, 6)
            x = (i % 2) * w if len(cards) > 2 else (i % 3) * 8
            y = (i // 2) * h
            dashcards.append(
                {
                    "id": -(i + 1),
                    "card_id": cid,
                    "row": y,
                    "col": x,
                    "size_x": w if len(cards) > 2 else 12,
                    "size_y": h,
                }
            )
        r = s.put(
            f"{MB}/api/dashboard/{did}", json={"dashcards": dashcards}, timeout=30
        )
        r.raise_for_status()
        return did

    d1 = dashboard(
        "Executive Summary", [c_ca_day, c_ca_30, c_top5_day]
    )
    d2 = dashboard(
        "Top Sellers", [c_top10_month, c_top3_evol, c_inactive]
    )
    d3 = dashboard(
        "Finance & Catalogue", [c_commissions, c_cat]
    )
    d4 = dashboard(
        "Fraude potentielle", [c_fraud_count, c_fraud_price, c_fraud_cancel]
    )
    print("    dashboards :", d1, d2, d3, d4)
    print()
    print("OK -> http://localhost:3000  (login :", EMAIL, "/", PASSWORD, ")")


if __name__ == "__main__":
    main()
