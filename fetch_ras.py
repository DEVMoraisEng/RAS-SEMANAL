# -*- coding: utf-8 -*-
"""
fetch_ras.py
------------
Lê os bancos da RAS no Notion e gera os JSON que o site consome:
  dist/data_atividades.json
  dist/data_obras.json

O site lê apenas esses JSON (nada de token no navegador -> sem CORS).

USO LOCAL (teste):
    export NOTION_TOKEN="ntn_xxx"          # o SEU token (rotacione o que foi exposto)
    python3 fetch_ras.py                   # gera os JSON em ./dist

NO GITHUB ACTIONS:
    o token vem de secret; os DB IDs já estão abaixo (pode sobrescrever por env).
"""

import os, json, time, datetime, unicodedata, urllib.request, urllib.error

TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
DB_ATIV  = os.environ.get("RAS_ATIVIDADES_DB_ID", "3b4c5ab532d380b2a5acd915bda9021c").strip()
DB_OBRAS = os.environ.get("RAS_OBRAS_DB_ID",      "3b4c5ab532d3806ba64bcf67f2dd4d6b").strip()
NOTION_VERSION = "2022-06-28"

def query(db):
    """Retorna todas as linhas do banco (com paginação)."""
    results, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        req = urllib.request.Request(
            f"https://api.notion.com/v1/databases/{db}/query",
            data=json.dumps(body).encode("utf-8"), method="POST")
        req.add_header("Authorization", "Bearer " + TOKEN)
        req.add_header("Notion-Version", NOTION_VERSION)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Erro Notion {e.code}: {e.read().decode('utf-8')[:400]}")
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.2)
    return results

def pval(prop):
    """Lê o valor de uma propriedade seja qual for o tipo (tolerante a mudanças)."""
    if prop is None:
        return ""
    t = prop.get("type")
    if t == "title":       return "".join(x["plain_text"] for x in prop["title"])
    if t == "rich_text":   return "".join(x["plain_text"] for x in prop["rich_text"])
    if t == "select":      return (prop.get("select") or {}).get("name", "")
    if t == "status":      return (prop.get("status") or {}).get("name", "")
    if t == "multi_select": return ", ".join(o["name"] for o in prop.get("multi_select", []))
    if t == "date":        return (prop.get("date") or {}).get("start", "")
    if t == "checkbox":    return "Sim" if prop.get("checkbox") else "Não"
    if t == "number":      return prop.get("number")
    if t == "people":      return ", ".join(p.get("name", "") for p in prop.get("people", []))
    return ""

def g(props, *names):
    """Pega a 1ª propriedade existente entre os nomes dados (tolera renome/maiúsculas)."""
    for n in names:
        if n in props:
            return pval(props[n])
    return ""

def _sa(s):
    """minúsculo e sem acento, para comparar nomes com tolerância."""
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower().strip()


def curto(nome_conta):
    """Nome de conta do Notion (vem completo, ex.: 'Júlio César Gomes de
    Morais Filho') -> nome curto que o site usa em RESP_LOCK ('Júlio').

    É isso que faz o <select> de Responsável da Diretoria casar a opção certa:
    sem essa conversão o nome completo não bate com 'Júlio'/'João Vitor' e o
    select cai sempre na 1ª opção, ignorando quem está no Notion.

    Sem acento e case-insensitive, tolerante a sobrenomes. Se não reconhecer
    ninguém, devolve '' e o chamador mantém o nome original do Notion.
    """
    k = _sa(nome_conta)
    if "hudson" in k:            return "Hudson"
    if k.startswith("lohany"):   return "Lohany"
    if k.startswith("julio"):    return "Júlio"
    if "joao vitor" in k:        return "João Vitor"
    if k.startswith("felipe"):   return "Felipe"
    if k.startswith("paula"):    return "Paula"   # 'paula...' sim, 'ana paula' não
    return ""


def build_atividades():
    out = []
    for pg in query(DB_ATIV):
        P = pg["properties"]
        resp_raw = g(P, "Responsável", "Responsavel")
        out.append({
            "id":          pg["id"],
            "nome":        g(P, "Nome", "Atividade"),
            "setor":       g(P, "Setor"),
            "responsavel": curto(resp_raw) or resp_raw,   # nome curto p/ casar no site
            "prioridade":  g(P, "Prioridade"),
            "status":      g(P, "Status"),
            "semana":      g(P, "Semana"),
            "obs":         g(P, "Observações", "Observacoes"),
            # ITEM 2 (03/09/2026) — de onde a atividade veio. A coluna Origem é
            # gravada pelo Code.gs quando a atividade nasce por coparticipação
            # ou vem replicada de outra RAS. Banco sem a coluna devolve "" e o
            # site simplesmente não mostra o selo.
            "origem":      g(P, "Origem"),
        })
    return out

def build_obras():
    out = []
    for pg in query(DB_OBRAS):
        P = pg["properties"]
        out.append({
            "id":          pg["id"],
            "nome":        g(P, "Nome", "Obra"),
            "cidade":      g(P, "CIDADE", "Cidade"),
            "setor":       g(P, "SETOR", "Setor"),
            "mes":         g(P, "Mês", "Mes"),
            "status":      g(P, "Status"),
            # ITEM 5 (03/09/2026) — colunas renomeadas no Notion:
            #   "Entrega prevista" -> "Previsão de início"
            #   "Prioritária"      -> "LIBERADA PARA INICIAR"
            # Os nomes antigos ficam na lista: banco ainda não renomeado
            # continua sendo lido sem erro.
            "previsao":    g(P, "Previsão de início", "Previsao de inicio",
                              "PREVISÃO DE INÍCIO", "Entrega prevista", "Entrega"),
            "liberada":    g(P, "LIBERADA PARA INICIAR", "Liberada para iniciar",
                              "Liberada", "Prioritária", "Prioritaria"),
            "obs":         g(P, "Observações", "Observacoes"),
        })
    return out

def status_options(db, *col_names):
    """Lê o schema do banco e devolve as opções da coluna Status na ORDEM
    definida no Notion. Funciona tanto para coluna do tipo 'status' quanto
    'select'. É isso que faz o dropdown do site espelhar o Notion: se você
    criar/renomear/remover uma opção lá, ela aparece/some no site sozinha.
    """
    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{db}", method="GET")
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Notion-Version", NOTION_VERSION)
    try:
        with urllib.request.urlopen(req) as r:
            schema = json.loads(r.read().decode("utf-8")).get("properties", {})
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Erro Notion {e.code} (schema {db}): {e.read().decode('utf-8')[:400]}")
    for n in col_names:
        prop = schema.get(n)
        if not prop:
            continue
        t = prop.get("type")
        if t in ("status", "select"):
            return [o["name"] for o in (prop.get(t) or {}).get("options", [])]
    return []


def main():
    if not TOKEN:
        raise SystemExit("Defina NOTION_TOKEN (o seu token do Notion).")
    os.makedirs("dist", exist_ok=True)
    now = datetime.datetime.now().isoformat(timespec="seconds")

    ativ = build_atividades()
    ativ_status = status_options(DB_ATIV, "Status")
    json.dump({"geradoEm": now, "statusOptions": ativ_status, "atividades": ativ},
              open("dist/data_atividades.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"data_atividades.json  -> {len(ativ)} atividades | status: {ativ_status}")

    obras = build_obras()
    obras_status = status_options(DB_OBRAS, "Status")
    # Opções da coluna "LIBERADA PARA INICIAR" na ordem do Notion — é isso que
    # faz o <select> do site gravar exatamente "SIM"/"NÃO" como está lá.
    liberada_opts = status_options(DB_OBRAS, "LIBERADA PARA INICIAR",
                                   "Liberada para iniciar", "Liberada",
                                   "Prioritária", "Prioritaria")
    json.dump({"geradoEm": now, "statusOptions": obras_status,
               "liberadaOptions": liberada_opts, "obras": obras},
              open("dist/data_obras.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"data_obras.json       -> {len(obras)} obras | status: {obras_status}")
    print(f"  liberada: {liberada_opts}")

if __name__ == "__main__":
    main()
