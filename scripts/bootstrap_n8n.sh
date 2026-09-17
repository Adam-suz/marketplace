#!/usr/bin/env bash
# Importe les 4 workflows + les 3 credentials dans n8n (export pre-configure).
# Usage : bash scripts/bootstrap_n8n.sh   (apres docker compose up -d)

set -e
cd "$(dirname "$0")/.."

echo "Attente de n8n..."
for i in $(seq 1 30); do
  curl -sf http://localhost:5678/healthz >/dev/null 2>&1 && break
  sleep 2
done
curl -sf http://localhost:5678/healthz >/dev/null || { echo "n8n ne repond pas"; exit 1; }

echo "Copie des fichiers dans le conteneur..."
docker exec mp_n8n mkdir -p /home/node/backup
docker cp n8n/export/credentials.json mp_n8n:/home/node/backup/credentials.json
docker cp n8n/export/workflows/. mp_n8n:/home/node/backup/workflows/

echo "Import des credentials..."
docker exec mp_n8n sh -c "n8n import:credentials --input=/home/node/backup/credentials.json"

echo "Import des workflows..."
docker exec mp_n8n sh -c "n8n import:workflow --separate --input=/home/node/backup/workflows/"

echo ""
echo "OK : 4 workflows + 3 credentials importes."
echo "Ouvrir http://localhost:5678 -> les credentials sont deja rattaches aux noeuds."
echo "Reste a faire : activer les workflows (toggle Active) si vous voulez le schedule,"
echo "et executer wf1 puis wf2 pour charger les donnees."
