# -*- coding: utf-8 -*-
"""
rollover_semana.py
-------------------
Roda automaticamente toda SEGUNDA de madrugada (via GitHub Actions).
Para toda atividade com Status != "Concluído" e Semana de uma semana passada,
atualiza a Semana para a segunda-feira da semana atual.

Assim, o que ficou "Em Andamento" ou "A Fazer" aparece sozinho no quadro da
semana vigente -- sem precisar copiar nada manualmente. O que foi concluído
mantém a Semana em que foi fechado (o histórico não se mexe).

USO LOCAL (teste):
    export NOTION_TOKEN="ntn_xxx"
    python3 rollover_semana.py            # aplica de verdade
    python3 rollover_semana.py --dry-run  # só mostra o que faria, sem alterar
"""

import os, sys, json, time, datetime, urllib.request, urllib.error
from zoneinfo import ZoneInfo

TOKEN  = os.environ.get("NOTION_TOKEN", "").strip()
DB_ATIV = os.environ.get("RAS_ATIVIDADES_DB_ID", "3b4c5ab532d380b2a5acd915bda9021c").strip()
NOTION_VERSION = "2022-06-28"
TZ = ZoneInfo("America/Sao_Paulo")
DRY_RUN = "--dry-run" in sys.argv

def monday_of_this_week(d):
    return d - datetime.timedelta(days=d.weekday())  # weekday(): segunda=0

def api(method, path, body=None):
    req = urllib.request.Request(
        "https://api.notion.com/v1" + path,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))

def query_all(db):
    results, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor: body["start_cursor"] = cursor
        data = api("POST", f"/databases/{db}/query", body)
        results.extend(data.get("results", []))
        if not data.get("has_more"): break
        cursor = data.get("next_cursor")
        time.sleep(0.15)
    return results

def main():
    if not TOKEN:
        raise SystemExit("Defina NOTION_TOKEN antes de rodar.")
    today = datetime.datetime.now(TZ).date()
    nova_semana = monday_of_this_week(today).isoformat()
    print(f"Semana atual (segunda-feira): {nova_semana}")

    rows = query_all(DB_ATIV)
    moved = 0
    for pg in rows:
        P = pg["properties"]
        status = (P.get("Status", {}).get("select") or {}).get("name", "")
        semana = (P.get("Semana", {}).get("date") or {}).get("start", "")
        nome = "".join(t["plain_text"] for t in P.get("Nome", {}).get("title", []))
        if not semana or status == "Concluído":
            continue
        if semana >= nova_semana:
            continue  # já é a semana atual (ou futura) — não mexe
        moved += 1
        print(f"  -> {nome[:60]!r}: {semana} => {nova_semana}  (status={status})")
        if not DRY_RUN:
            api("PATCH", f"/pages/{pg['id']}", {
                "properties": {"Semana": {"date": {"start": nova_semana}}}
            })
            time.sleep(0.2)

    print(f"\n{'(dry-run) ' if DRY_RUN else ''}{moved} atividade(s) movida(s) para {nova_semana}.")

if __name__ == "__main__":
    main()
