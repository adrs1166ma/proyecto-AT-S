"""
build_ping_workflow.py — Generador del workflow n8n "Ping Servicios - Keep Alive"

Uso:
    python n8n/build_ping_workflow.py   → genera n8n/ping-workflow.json

Hace ping cada 14 minutos a los servicios en Render para evitar que se duerman.
Editar aqui en vez de editar el JSON directamente.
"""

import json
from pathlib import Path

OUTPUT = Path(__file__).parent / "ping-workflow.json"

# ─────────────────────────────────────────────
# Helpers (mismo patron que build_workflow.py)
# ─────────────────────────────────────────────

def node(id_, name, type_, params, pos, type_version=None, always_output=False, credentials=None):
    n = {
        "parameters": params,
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": type_version or _default_version(type_),
        "position": pos,
    }
    if always_output:
        n["alwaysOutputData"] = True
    if credentials:
        n["credentials"] = credentials
    return n

def _default_version(t):
    defaults = {
        "n8n-nodes-base.scheduleTrigger": 1.2,
        "n8n-nodes-base.httpRequest": 4.2,
        "n8n-nodes-base.if": 2,
    }
    return defaults.get(t, 1)

def conn(from_node, to_nodes):
    """to_nodes: str | list[str] — lista de nodos destino (output 0 a N)"""
    if isinstance(to_nodes, str):
        to_nodes = [[to_nodes]]
    if isinstance(to_nodes[0], str):
        return {"main": [[{"node": n, "type": "main", "index": 0} for n in to_nodes]]}
    return {"main": [[{"node": n, "type": "main", "index": 0} for n in branch] for branch in to_nodes]}

# ─────────────────────────────────────────────
# NODOS
# ─────────────────────────────────────────────

NODES = [
    node(
        "schedule-trigger-01",
        "Schedule Trigger",
        "n8n-nodes-base.scheduleTrigger",
        {"rule": {"interval": [{"field": "minutes", "minutesInterval": 14}]}},
        pos=[240, 300],
        type_version=1.2,
    ),
    node(
        "http-ping-python-01",
        "Ping Python Service",
        "n8n-nodes-base.httpRequest",
        {
            "method": "GET",
            "url": "https://proyecto-at-s.onrender.com/",
            "options": {"timeout": 10000},
        },
        pos=[480, 300],
        type_version=4.2,
    ),
]

# ─────────────────────────────────────────────
# CONEXIONES
# ─────────────────────────────────────────────

CONNECTIONS = {
    "Schedule Trigger": conn("Schedule Trigger", "Ping Python Service"),
}

# ─────────────────────────────────────────────
# BUILD
# ─────────────────────────────────────────────

def build():
    workflow = {
        "name": "Ping Servicios - Keep Alive",
        "nodes": NODES,
        "connections": CONNECTIONS,
        "active": True,
        "settings": {
            "executionOrder": "v1",
        },
        "tags": [],
    }

    OUTPUT.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generado: {OUTPUT}")
    print(f"Nodos: {len(NODES)}")

if __name__ == "__main__":
    build()
