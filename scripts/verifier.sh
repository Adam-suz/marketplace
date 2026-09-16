#!/usr/bin/env bash
# Verification du pipeline Marketplace (a lancer depuis la racine du projet).
# Usage : bash scripts/verifier.sh [DATE]     (defaut : derniere date chargee)

set -euo pipefail

PSQL="docker exec mp_postgres_dwh psql -U dwh_user -d dwh -t -A"
DT="${1:-}"

echo "== 1. Services Docker =="
docker compose ps --format "table {{.Name}}\t{{.Status}}"

echo
echo "== 2. API Marketplace =="
curl -s http://localhost:5000/health && echo
curl -s -o /dev/null -w "sans token -> HTTP %{http_code} (401 attendu)\n" \
  "http://localhost:5000/orders?date=2026-04-07"

echo
echo "== 3. Dimensions =="
$PSQL -c "SELECT 'dim_seller: ' || COUNT(*) FROM dwh.dim_seller;"
$PSQL -c "SELECT 'dim_product: ' || COUNT(*) FROM dwh.dim_product;"
$PSQL -c "SELECT 'dim_date: ' || COUNT(*) FROM dwh.dim_date;"

echo
echo "== 4. Idempotence =="
if [ -z "$DT" ]; then
  DT=$($PSQL -c "SELECT max(dt) FROM dwh.fact_orders;")
  echo "   (date detectee : $DT)"
fi
N=$($PSQL -c "SELECT COUNT(*) FROM dwh.fact_orders WHERE dt='$DT';")
echo "   fact_orders dt=$DT -> $N lignes"
echo "   => Rejouer le workflow n8n sur la meme date puis relancer ce script :"
echo "      le COUNT doit rester $N (pas 2x)."

echo
echo "== 5. Analytics =="
$PSQL -c "SELECT 'daily_summary: ' || COUNT(*) || ' jours' FROM analytics.daily_summary;"
$PSQL -c "SELECT dt, total_orders, total_revenue FROM analytics.daily_summary ORDER BY dt DESC LIMIT 3;"

echo
echo "== 6. Objets MinIO =="
docker exec mp_minio mc alias set local http://localhost:9000 minioadmin minioadmin123 >/dev/null
docker exec mp_minio mc ls --recursive local/data-lake/ | head -10
