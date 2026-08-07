# -*- coding: utf-8 -*-
"""
corrigir_semana.py  (uso ÚNICO / manual)
----------------------------------------
Conserta o efeito de um rollover que rodou fora de hora e empurrou as
atividades para a semana ERRADA. Move todas as atividades cuja Semana == DE
para a Semana == PARA (não mexe em mais nada; status é preservado).

No caso atual:
    DE   = 2026-08-10  (para onde o rollover de quinta empurrou tudo)
    PARA = 2026-08-03  (a semana atual correta)

USO:
    export NOTION_TOKEN="ntn_xxx"
    python3 corrigir_semana.py --dry-run                 # mostra o que faria
    python3 corrigir_semana.py                           # aplica (DE/PARA padrão)
    python3 corrigir_semana.py --de 2026-08-10 --para 2026-08-03   # explícito

Depois de rodar, rode fetch_ras.py para regerar os JSON do site
(ou dispare o workflow "RAS - atualizar dados").
"""

import os, sys, json, time, urllib.request, urllib.error

TOKEN   = os.environ.get("NOTION_TOKEN", "").strip()
DB_ATIV = os.environ.get("RAS_ATIVIDADES_DB_ID", "3b4c5ab532d380b2a5acd915bda9021c").strip()
NOTION_VERSION = "2022-06-28"

def arg(flag, default):
    return sys.argv[sys.argv.index(flag)+1] if flag in sys.argv else default

DRY_RUN = "--dry-run" in sys.argv
DE   = arg("--de",   "2026-08-10")
PARA = arg("--para", "2026-08-03")

NOMES_SEMANA = ["Semana"]
NOMES_NOME   = ["Nome", "Atividade"]

def api(method, path, body=None):
    req = urllib.request.Request(
        "https://api.notion.com/v1" + path,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Erro Notion {e.code} em {method} {path}: {e.read().decode('utf-8')[:400]}")

def achar(schema, candidatos):
    for n in candidatos:
        if n in schema:
            return n
    return None

def ler_semana(prop):
    if not prop: return ""
    return (prop.get("date") or {}).get("start", "")

def ler_nome(prop):
    if not prop or prop.get("type") != "title": return ""
    return "".join(t["plain_text"] for t in prop.get("title", []))

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
    schema = api("GET", f"/databases/{DB_ATIV}").get("properties", {})
    p_semana = achar(schema, NOMES_SEMANA)
    p_nome   = achar(schema, NOMES_NOME)
    if not p_semana:
        raise SystemExit(f"Não encontrei a coluna Semana. Colunas: {list(schema)}")

    print(f"Movendo atividades da semana {DE}  ->  {PARA}")
    rows = query_all(DB_ATIV)
    n = 0
    for pg in rows:
        P = pg["properties"]
        semana = ler_semana(P.get(p_semana))
        nome   = ler_nome(P.get(p_nome)) if p_nome else ""
        if (semana or "")[:10] != DE:
            continue
        n += 1
        print(f"  -> {nome[:60]!r}: {DE} => {PARA}")
        if not DRY_RUN:
            api("PATCH", f"/pages/{pg['id']}", {"properties": {
                p_semana: {"date": {"start": PARA}},
            }})
            time.sleep(0.2)

    print(f"\n{'(dry-run) ' if DRY_RUN else ''}{n} atividade(s) {'seriam ' if DRY_RUN else ''}movida(s) de {DE} para {PARA}.")

if __name__ == "__main__":
    main()
