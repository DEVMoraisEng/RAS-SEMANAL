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

import os, json, time, datetime, urllib.request, urllib.error

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

def build_atividades():
    out = []
    for pg in query(DB_ATIV):
        P = pg["properties"]
        out.append({
            "id":          pg["id"],
            "nome":        g(P, "Nome", "Atividade"),
            "setor":       g(P, "Setor"),
            "responsavel": g(P, "Responsável", "Responsavel"),
            "prioridade":  g(P, "Prioridade"),
            "status":      g(P, "Status"),
            "semana":      g(P, "Semana"),
            "obs":         g(P, "Observações", "Observacoes"),
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
            "entrega":     g(P, "Entrega prevista", "Entrega"),
            "prioritaria": g(P, "Prioritária", "Prioritaria"),
            "obs":         g(P, "Observações", "Observacoes"),
        })
    return out

def main():
    if not TOKEN:
        raise SystemExit("Defina NOTION_TOKEN (o seu token do Notion).")
    os.makedirs("dist", exist_ok=True)
    now = datetime.datetime.now().isoformat(timespec="seconds")

    ativ = build_atividades()
    json.dump({"geradoEm": now, "atividades": ativ},
              open("dist/data_atividades.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"data_atividades.json  -> {len(ativ)} atividades")

    obras = build_obras()
    json.dump({"geradoEm": now, "obras": obras},
              open("dist/data_obras.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"data_obras.json       -> {len(obras)} obras")

if __name__ == "__main__":
    main()
