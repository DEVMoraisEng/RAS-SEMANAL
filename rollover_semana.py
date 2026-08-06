# -*- coding: utf-8 -*-
"""
rollover_semana.py
-------------------
Roda automaticamente todo DOMINGO à noite (via GitHub Actions).

Para toda atividade que NÃO foi concluída e cuja Semana pertence a uma semana
já encerrada, o script:
  - muda a Semana para a segunda-feira da PRÓXIMA semana;
  - muda o Status para "Continuidade da Semana Anterior".

Assim, o que ficou em aberto reaparece sozinho no quadro da nova semana, já
sinalizado como pendência arrastada. O que foi concluído fica no histórico.

Tolerância: a coluna Status pode ser do tipo "select" OU "status" no Notion;
os nomes das colunas podem variar (Nome/Atividade, etc.). O script lê o schema
antes de agir — mesma lógica do fetch_ras.py.

USO LOCAL (teste):
    export NOTION_TOKEN="ntn_xxx"
    python3 rollover_semana.py            # aplica de verdade
    python3 rollover_semana.py --dry-run  # só mostra o que faria, sem alterar
"""

import os, sys, json, time, datetime, urllib.request, urllib.error
from zoneinfo import ZoneInfo

TOKEN   = os.environ.get("NOTION_TOKEN", "").strip()
DB_ATIV = os.environ.get("RAS_ATIVIDADES_DB_ID", "3b4c5ab532d380b2a5acd915bda9021c").strip()
NOTION_VERSION = "2022-06-28"
TZ = ZoneInfo("America/Sao_Paulo")
DRY_RUN = "--dry-run" in sys.argv

STATUS_CONCLUIDO    = "Concluído"
STATUS_CONTINUIDADE = "Continuidade da Semana Anterior"

# nomes possíveis de cada coluna (tolera renome/acentos)
NOMES = {
    "status": ["Status"],
    "semana": ["Semana"],
    "nome":   ["Nome", "Atividade"],
}

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

def get_schema(db):
    return api("GET", f"/databases/{db}").get("properties", {})

def achar(schema, candidatos):
    for n in candidatos:
        if n in schema:
            return n
    return None

def ler_status(prop):
    if not prop: return ""
    t = prop.get("type")
    if t == "status": return (prop.get("status") or {}).get("name", "")
    if t == "select": return (prop.get("select") or {}).get("name", "")
    return ""

def ler_semana(prop):
    if not prop: return ""
    return (prop.get("date") or {}).get("start", "")

def ler_nome(prop):
    if not prop or prop.get("type") != "title": return ""
    return "".join(t["plain_text"] for t in prop.get("title", []))

def valor_status(tipo, nome):
    # monta o valor de Status conforme o tipo real da coluna
    if tipo == "status":
        return {"status": {"name": nome}}
    return {"select": {"name": nome}}

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

def proxima_segunda(d):
    """Segunda-feira que inicia a próxima semana em relação a d."""
    dias = (0 - d.weekday()) % 7   # weekday(): segunda=0 ... domingo=6
    if dias == 0:                  # se hoje já é segunda, vai para a seguinte
        dias = 7
    return d + datetime.timedelta(days=dias)

def main():
    if not TOKEN:
        raise SystemExit("Defina NOTION_TOKEN antes de rodar.")

    schema = get_schema(DB_ATIV)
    p_status = achar(schema, NOMES["status"])
    p_semana = achar(schema, NOMES["semana"])
    p_nome   = achar(schema, NOMES["nome"])
    if not p_status or not p_semana:
        raise SystemExit(f"Não encontrei as colunas Status/Semana. Colunas do banco: {list(schema)}")

    tipo_status = schema[p_status]["type"]
    if tipo_status not in ("status", "select"):
        raise SystemExit(f'A coluna "{p_status}" é do tipo {tipo_status}; esperado status ou select.')

    # Se for tipo "status", a opção precisa existir no Notion — a API NÃO cria
    # opção de status sozinha (diferente de select).
    if tipo_status == "status":
        opcoes = [o["name"] for o in schema[p_status].get("status", {}).get("options", [])]
        if STATUS_CONTINUIDADE not in opcoes:
            raise SystemExit(
                f'A opção "{STATUS_CONTINUIDADE}" não existe na coluna Status (tipo status).\n'
                f'Opções atuais no Notion: {opcoes}\n'
                f'Crie essa opção no Notion antes de rodar (a API não cria opção de status automaticamente).')

    hoje = datetime.datetime.now(TZ).date()
    alvo = proxima_segunda(hoje).isoformat()
    print(f"Hoje: {hoje} | Movendo pendências para a semana de: {alvo}")

    rows = query_all(DB_ATIV)
    movidas = 0
    for pg in rows:
        P = pg["properties"]
        status = ler_status(P.get(p_status))
        semana = ler_semana(P.get(p_semana))
        nome   = ler_nome(P.get(p_nome)) if p_nome else ""
        if not semana or status == STATUS_CONCLUIDO:
            continue
        if semana >= alvo:
            continue  # já está na próxima semana (ou em semana futura) — não mexe
        movidas += 1
        print(f"  -> {nome[:60]!r}: semana {semana} => {alvo} | status {status!r} => {STATUS_CONTINUIDADE!r}")
        if not DRY_RUN:
            api("PATCH", f"/pages/{pg['id']}", {"properties": {
                p_semana: {"date": {"start": alvo}},
                p_status: valor_status(tipo_status, STATUS_CONTINUIDADE),
            }})
            time.sleep(0.2)

    print(f"\n{'(dry-run) ' if DRY_RUN else ''}{movidas} atividade(s) movida(s) para {alvo}.")

if __name__ == "__main__":
    main()
