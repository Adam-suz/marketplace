"""Tests pytest sur les workflows n8n.

Equivalent des tests DagBag du cahier des charges : au lieu de verifier
les DAGs Airflow (non utilises ici), on verifie que les workflows n8n
sont des artefacts valides et que le pipeline respecte les regles
imposees (trigger, idempotence, pas de secret en dur).

Lancer : pytest tests/test_workflows.py -v   (aucun service requis)
"""

import json
from pathlib import Path

N8N_DIR = Path(__file__).resolve().parent.parent / "n8n"
WF_FILES = [
    "wf1_dims_refresh_daily.json",
    "wf2_orders_ingest_daily.json",
    "wf3_anomaly_detect_daily.json",
    "wf4_analytics_aggregate.json",
]
TRIGGER_TYPES = {
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.executeWorkflowTrigger",
}


def load(name: str) -> dict:
    return json.loads((N8N_DIR / name).read_text(encoding="utf-8"))


def test_all_workflows_are_valid_json():
    """Equivalent 'no import errors' : chaque workflow est importable."""
    for f in WF_FILES:
        wf = load(f)
        assert wf["nodes"], f"{f}: aucun noeud"
        assert wf["connections"], f"{f}: aucune connexion"


def test_each_workflow_has_a_trigger():
    for f in WF_FILES:
        types = {n["type"] for n in load(f)["nodes"]}
        assert types & TRIGGER_TYPES, f"{f}: pas de trigger"


def test_orders_ingest_has_idempotent_transform():
    """Pattern obligatoire du CDC : DELETE + INSERT par partition dt."""
    wf = load("wf2_orders_ingest_daily.json")
    code = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.code")
    js = code["parameters"]["jsCode"]
    assert "DELETE FROM dwh.fact_orders WHERE dt=" in js
    assert "INSERT INTO dwh.fact_orders" in js
    # et le purge precede bien le load dans le graphe
    successors = wf["connections"]["Purger fact (dt)"]["main"][0]
    assert successors[0]["node"] == "Alimenter fact_orders"


def test_raw_layer_partitioned_by_dt():
    """Le JSON brut doit etre archive dans data-lake sous dt=YYYY-MM-DD."""
    wf = load("wf2_orders_ingest_daily.json")
    s3 = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.s3")
    assert s3["parameters"]["bucketName"] == "data-lake"
    code = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.code")
    assert "dt=" in code["parameters"]["jsCode"]


def test_analytics_aggregation_is_a_separate_workflow():
    """wf4 est decouple : declenche par wf2 via executeWorkflowTrigger."""
    wf4 = load("wf4_analytics_aggregate.json")
    types = {n["type"] for n in wf4["nodes"]}
    assert "n8n-nodes-base.executeWorkflowTrigger" in types
    wf2 = load("wf2_orders_ingest_daily.json")
    assert any(
        n["type"] == "n8n-nodes-base.executeWorkflow" for n in wf2["nodes"]
    )


def test_no_hardcoded_token():
    """Le token API doit vivre dans un credential n8n, pas dans le workflow."""
    for f in WF_FILES:
        assert "formation-token-2026" not in (N8N_DIR / f).read_text(
            encoding="utf-8"
        )
