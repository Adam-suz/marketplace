"""API Marketplace simulee — remplace le backoffice de Maelys.

Deterministe : seed = md5(cle). Une meme date = memes commandes,
ce qui permet de tester l'idempotence du pipeline.

Auth : Bearer token sur tous les endpoints sauf /health.
"""

import hashlib
import random
from functools import wraps

from flask import Flask, jsonify, request

app = Flask(__name__)

TOKEN = "formation-token-2026"
COMMISSION_RATE = 0.12

# ---------------------------------------------------------------------------
# Donnees de reference (generees de facon deterministe)
# ---------------------------------------------------------------------------

SHOP_PREFIXES = [
    "Atelier", "Maison", "Boutique", "Studio", "Les", "La", "Le", "Chez",
    "Domaine", "Marque",
]
SHOP_NAMES = [
    "Bleu", "Rouge", "Verger", "Lumiere", "Nord", "Sud", "Prairie", "Lin",
    "Fauve", "Racine", "Braise", "Opaline", "Cedre", "Brume", "Sel",
    "Papillon", "Garance", "Orme", "Sauge", "Velours",
]
CITIES = [
    "Paris", "Lyon", "Marseille", "Bordeaux", "Nantes", "Lille",
    "Toulouse", "Strasbourg", "Rennes", "Nice", "Montpellier", "Dijon",
]
CATEGORIES = [
    "Mode", "Maison", "Beaute", "Alimentation", "Sport",
    "High-Tech", "Jardin", "Enfants", "Bijoux", "Papeterie",
]
PRODUCT_WORDS = [
    "Sac", "Lampe", "Creme", "The", "Tapis", "Montre", "Vase", "Bougie",
    "Echarpe", "Carnet", "Bracelet", "Huile", "Poster", "Gourde", "Savon",
    "Miroir", "Coussin", "Panier", "Collier", "Plaid",
]
PRODUCT_ADJECTIVES = [
    "bleu", "rouge", "vert", "nature", "dore", "argent", "vintage",
    "bio", "artisanal", "minimaliste", "lin", "chene", "cuir", "coton",
    "ceramique", "pastel", "nordique", "industriel", "floral", "graphique",
]
FIRST_NAMES = [
    "Alice", "Bruno", "Chloe", "David", "Emma", "Felix", "Gaelle", "Hugo",
    "Ines", "Jules", "Karim", "Lea", "Marc", "Nina", "Oscar", "Pauline",
]
LAST_NAMES = [
    "Martin", "Bernard", "Dubois", "Petit", "Durand", "Leroy", "Moreau",
    "Simon", "Laurent", "Michel", "David", "Roux", "Fournier", "Girard",
]

# Volumetrie du cahier des charges : 2400 vendeurs, 180k produits,
# ~8500 commandes/jour, ~4.2 MEUR de CA mensuel.
NB_SELLERS = 2400
NB_PRODUCTS = 180_000
NB_CUSTOMERS = 25_000


def _rng(key: str) -> random.Random:
    """RNG deterministe a partir d'un hash md5 de la cle."""
    seed = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return random.Random(seed)


def _gen_sellers() -> list[dict]:
    r = _rng("sellers")
    sellers = []
    for i in range(1, NB_SELLERS + 1):
        name = (
            f"{r.choice(SHOP_PREFIXES)} {r.choice(SHOP_NAMES)} "
            f"{r.choice(SHOP_NAMES)}"
        )
        sellers.append(
            {
                "seller_id": f"S{i:04d}",
                "name": name,
                "country": "FR" if r.random() < 0.9 else r.choice(
                    ["BE", "ES", "IT", "DE"]
                ),
                "city": r.choice(CITIES),
                "joined_date": (
                    f"{r.randint(2021, 2025)}-"
                    f"{r.randint(1, 12):02d}-{r.randint(1, 28):02d}"
                ),
                "rating": round(r.uniform(3.0, 5.0), 1),
            }
        )
    return sellers


def _gen_products(sellers: list[dict]) -> list[dict]:
    r = _rng("products")
    products = []
    for i in range(1, NB_PRODUCTS + 1):
        seller = r.choice(sellers)
        products.append(
            {
                "product_id": f"P{i:04d}",
                "name": (
                    f"{r.choice(PRODUCT_WORDS)} "
                    f"{r.choice(PRODUCT_ADJECTIVES)}"
                ),
                "category": r.choice(CATEGORIES),
                # prix bas/moyen -> panier moyen ~17 EUR, coherent avec
                # ~8500 cmd/jour et ~4.2 MEUR de CA mensuel
                "price": round(r.uniform(3.0, 20.0), 2),
                "seller_id": seller["seller_id"],
            }
        )
    return products


def _gen_customers() -> list[dict]:
    r = _rng("customers")
    customers = []
    for i in range(1, NB_CUSTOMERS + 1):
        customers.append(
            {
                "customer_id": f"C{i:04d}",
                "name": (
                    f"{r.choice(FIRST_NAMES)} {r.choice(LAST_NAMES)}"
                ),
                "city": r.choice(CITIES),
                "country": "FR",
            }
        )
    return customers


SELLERS = _gen_sellers()
PRODUCTS = _gen_products(SELLERS)
CUSTOMERS = _gen_customers()
_PRODUCT_BY_ID = {p["product_id"]: p for p in PRODUCTS}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


@app.get("/sellers")
@require_auth
def sellers():
    limit = request.args.get("limit", type=int)
    data = SELLERS[:limit] if limit else SELLERS
    return jsonify({"count": len(data), "sellers": data})


@app.get("/products")
@require_auth
def products():
    limit = request.args.get("limit", type=int)
    data = PRODUCTS[:limit] if limit else PRODUCTS
    return jsonify({"count": len(data), "products": data})


@app.get("/customers")
@require_auth
def customers():
    limit = request.args.get("limit", type=int)
    data = CUSTOMERS[:limit] if limit else CUSTOMERS
    return jsonify({"count": len(data), "customers": data})


@app.get("/orders")
@require_auth
def orders():
    date = request.args.get("date")
    if not date:
        return jsonify({"error": "parametre 'date' requis (YYYY-MM-DD)"}), 400

    r = _rng(f"orders:{date}")
    n_orders = 8000 + r.randint(0, 1000)  # ~8500 commandes/jour
    orders = []
    for i in range(1, n_orders + 1):
        product = r.choice(PRODUCTS)
        customer = r.choice(CUSTOMERS)
        qty = r.randint(1, 2)
        # prix parfois remise ou majoration legere
        unit_price = round(product["price"] * r.uniform(0.9, 1.1), 2)
        total = round(unit_price * qty, 2)
        orders.append(
            {
                "order_id": f"{date}-{i:04d}",
                "dt": date,
                "customer_id": customer["customer_id"],
                "seller_id": product["seller_id"],
                "product_id": product["product_id"],
                "quantity": qty,
                "unit_price": unit_price,
                "total": total,
                "commission": round(total * COMMISSION_RATE, 2),
                "status": r.choices(
                    ["completed", "shipped", "pending", "cancelled"],
                    weights=[70, 15, 10, 5],
                )[0],
            }
        )
    return jsonify({"date": date, "count": len(orders), "orders": orders})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
