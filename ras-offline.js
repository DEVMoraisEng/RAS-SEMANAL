/* ras-offline.js — RAS · Morais Engenharia  (IGUAL em todas as RAS)
 * ---------------------------------------------------------------------------
 * POR QUE EXISTE (21/09/2026): a internet caiu no meio da reunião e tudo o que
 * foi preenchido sumiu. O post() antigo mandava a gravação UMA vez e, se a rede
 * não estivesse lá, o pedido morria ali — e a tela, que só guardava tudo na
 * memória, perdia o resto ao recarregar.
 *
 * O que muda — o mesmo esquema do PORTAL-MORAIS:
 *   1) Toda gravação vira um item numa FILA guardada no navegador
 *      (localStorage) ANTES de tentar enviar. Fechar a aba, recarregar ou
 *      desligar o celular não perde nada.
 *   2) A fila é enviada em ordem, uma de cada vez, assim que der: ao abrir a
 *      página, quando a internet volta, a cada 20 s enquanto tiver item e toda
 *      vez que a aba volta para a frente.
 *   3) Ao abrir a página, o que ainda não está no arquivo publicado (dist/) é
 *      REAPLICADO por cima dos dados — quem recarrega vê o que preencheu, mesmo
 *      sem internet e mesmo antes do site republicar.
 *   4) O sw.js guarda o site e a última cópia dos dados, então a RAS ABRE sem
 *      internet (antes abria em branco ou com os dados de exemplo).
 *
 * Cada envio leva um "opId". Se a conexão cair DEPOIS de o Apps Script ter
 * gravado (o pedido chegou, a resposta não), a fila reenvia — e o Code.gs
 * reconhece o opId repetido e não cria a atividade duas vezes.
 *
 * ATENÇÃO — ORIGEM COMPARTILHADA: todos os sites DEVMoraisEng.github.io/...
 * (as RAS e o portal) dividem o MESMO localStorage. Por isso a chave da fila
 * leva a pasta do site ("/RAS-SEMANAL/") — cada RAS tem a sua fila e nenhuma
 * mexe na do portal ("morais_fila").
 * ------------------------------------------------------------------------- */
(function(){
  "use strict";

  const PASTA  = location.pathname.replace(/[^/]*$/, "") || "/";   // "/RAS-SEMANAL/"
  const CHAVE  = "ras_ops::" + PASTA;
  /* Depois de ENVIADA, a alteração continua sendo reaplicada na tela até
     aparecer um arquivo publicado gerado pelo menos MARGEM depois do envio —
     aí ela já está no Notion e o dado publicado passa a valer sozinho.
     A margem cobre a diferença de relógio entre o celular e o GitHub. */
  const MARGEM    = 3 * 60 * 1000;
  const VIDA_MAX  = 14 * 864e5;       // enviada há 14 dias e nunca publicada: descarta
  const TEMPO_MAX = 45000;            // um envio pendurado não pode travar a fila
  const INTERVALO = 20000;

  /* ---------------- armazenamento ---------------- */
  function ler(){
    try{ const a = JSON.parse(localStorage.getItem(CHAVE) || "[]"); return Array.isArray(a) ? a : []; }
    catch(e){ return []; }
  }
  function gravar(a){
    try{ localStorage.setItem(CHAVE, JSON.stringify(a)); return true; }
    catch(e){ console.warn("[ras-offline] não coube no navegador", e && e.name); return false; }
  }
  /* Mexe na fila SEMPRE relendo antes (outra aba pode ter mexido) e sem
     segurar a cópia através de um await — senão uma aba apagaria o que a
     outra acabou de guardar. */
  function mexer(fn){ const a = ler(); const r = fn(a); gravar(a); return r; }

  function novoId(){ return Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 9); }
  function endpoint(){ try{ return (typeof WRITE_ENDPOINT !== "undefined" && WRITE_ENDPOINT) || ""; }catch(e){ return ""; } }
  function avisar(msg){ try{ if(typeof toast === "function") toast(msg); }catch(e){} }

  /* "2026-09-21T07:42:51" (sem fuso) = UTC, igual ao mostrarUltimaAtualizacao() */
  function msDe(iso){
    if(!iso) return 0;
    const d = new Date(iso + (/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? "" : "Z"));
    return isNaN(d) ? 0 : d.getTime();
  }

  /* ---------------- entrada: o post() da página chama isto ---------------- */
  function enviar(dados, meta){
    meta = meta || {};
    const op = {
      opId: novoId(), ts: Date.now(), enviado: 0,
      dados: Object.assign({}, dados),
      localId: meta.localId || null,
      item: meta.item ? Object.assign({}, meta.item) : null
    };
    op.dados.opId = op.opId;
    const coube = mexer(a => { a.push(op); return true; }) && ler().some(o => o.opId === op.opId);
    if(!coube){
      /* Navegador sem espaço (raríssimo): não dá pra guardar, então pelo menos
         tenta mandar direto, como era antes. */
      avisar("Atenção: o navegador está sem espaço — esta alteração NÃO ficou guardada.");
      mandar(op.dados);
      return op.opId;
    }
    pintar();
    drenar();
    return op.opId;
  }

  /* ---------------- envio ---------------- */
  async function mandar(dados){
    const url = endpoint(); if(!url) return false;
    const qs = Object.entries(dados)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v ?? "")}`).join("&");
    const ctl = (typeof AbortController !== "undefined") ? new AbortController() : null;
    const t = ctl ? setTimeout(() => ctl.abort(), TEMPO_MAX) : 0;
    try{
      /* no-cors: a resposta é opaca, não dá pra ler. Mas o fetch só RESOLVE se
         o pedido chegou ao servidor e voltou; sem rede ele REJEITA — é esse o
         sinal que separa "enviado" de "ficar na fila". */
      await fetch(`${url}?${qs}`, { method:"GET", mode:"no-cors", cache:"no-store", signal: ctl ? ctl.signal : undefined });
      return true;
    }catch(e){ return false; }
    finally{ if(t) clearTimeout(t); }
  }

  let _drenando = false;
  async function drenar(){
    if(_drenando || !endpoint()) return;
    if(!pendentes()) { pintar(); return; }
    if(navigator.onLine === false){ pintar(); return; }
    _drenando = true; pintar();
    const rodar = async () => {
      for(let voltas = 0; voltas < 500; voltas++){
        const prox = ler().find(o => !o.enviado);
        if(!prox) break;
        const ok = await mandar(prox.dados);
        if(!ok) break;                         // rede caiu: para e tenta depois
        mexer(a => { const o = a.find(x => x.opId === prox.opId); if(o) o.enviado = Date.now(); });
        pintar();
      }
    };
    try{
      /* Duas abas da mesma RAS abertas: só uma envia de cada vez. */
      if(navigator.locks && navigator.locks.request){
        await navigator.locks.request(CHAVE, { ifAvailable:true }, lock => lock ? rodar() : null);
      } else {
        await rodar();
      }
    } finally {
      _drenando = false; pintar();
    }
  }

  function pendentes(){ return ler().filter(o => !o.enviado).length; }

  /* ---------------- reaplicar por cima dos dados publicados ----------------
   * Chamado no boot(), logo depois de ler o dist/. Devolve as listas já com
   * as alterações deste aparelho. */
  function aplicar(opts){
    let ativ  = Array.isArray(opts.ativ)  ? opts.ativ  : null;
    let obras = Array.isArray(opts.obras) ? opts.obras : null;
    const gerado = msDe(opts.geradoEm);
    const agora = Date.now();

    /* limpa o que o arquivo publicado já contém */
    const ops = mexer(a => {
      for(let i = a.length - 1; i >= 0; i--){
        const o = a[i];
        if(!o.enviado) continue;
        const publicado = gerado && gerado >= o.enviado + MARGEM;
        const velho = agora - o.enviado > VIDA_MAX;
        if(publicado || velho) a.splice(i, 1);
      }
      return a.slice();
    });

    ops.sort((x, y) => x.ts - y.ts).forEach(o => {
      const d = o.dados || {};
      switch(d.action){
        case "create":
          if(d.ras) return;                    // enviada para OUTRA RAS: não aparece aqui
          if(ativ && o.item && o.localId && !ativ.some(x => x.id === o.localId))
            ativ.push(Object.assign({}, o.item, { id:o.localId }));
          return;
        case "create_obra":
          if(obras && o.item && o.localId && !obras.some(x => x.id === o.localId))
            obras.push(Object.assign({}, o.item, { id:o.localId }));
          return;
        case "update":      { const x = ativ  && ativ.find(y => y.id === d.id);  if(x) x[d.field] = d.value; return; }
        case "update_obra": { const x = obras && obras.find(y => y.id === d.id); if(x) x[d.field] = d.value; return; }
        case "delete":      if(ativ)  ativ  = ativ.filter(y => y.id !== d.id);  return;
        case "delete_obra": if(obras) obras = obras.filter(y => y.id !== d.id); return;
      }
    });
    pintar();
    return { ativ: ativ || opts.ativ, obras: obras || opts.obras };
  }

  /* ---------------- itens criados neste aparelho ("local-...") ----------------
   * Uma atividade criada aqui só ganha o ID do Notion no próximo build. Até lá:
   *  - se a criação AINDA está na fila, editar/excluir mexe direto nela (a
   *    atividade já nasce certa no Notion, ou nem nasce);
   *  - se já foi enviada, não existe como editar pelo ID — a tela avisa. */
  function acharCriacao(a, localId){ return a.find(o => o.localId === localId); }

  function estado(localId){
    const o = acharCriacao(ler(), localId);
    if(!o) return null;
    return o.enviado ? "enviado" : "pendente";
  }
  function editarCriacao(localId, field, value){
    return mexer(a => {
      const o = acharCriacao(a, localId);
      if(!o || o.enviado) return false;
      const chave = (o.dados.action === "create" && field === "nome") ? "atividade" : field;
      o.dados[chave] = value;
      if(o.item) o.item[field] = value;
      return true;
    });
  }
  function cancelarCriacao(localId){
    const ok = mexer(a => {
      const i = a.findIndex(o => o.localId === localId && !o.enviado);
      if(i < 0) return false;
      a.splice(i, 1);
      return true;
    });
    pintar();
    return ok;
  }

  /* ---------------- faixa de status (canto inferior esquerdo) ---------------- */
  let _el = null, _okT = 0, _tinha = 0;
  function el(){
    if(_el || !document.body) return _el;
    const st = document.createElement("style");
    st.textContent =
      ".rasoff{position:fixed;left:14px;bottom:14px;z-index:9999;display:none;align-items:center;gap:10px;" +
      "max-width:calc(100vw - 28px);padding:9px 14px;border-radius:12px;font:600 12.5px/1.35 Inter,-apple-system,'Segoe UI',Roboto,sans-serif;" +
      "box-shadow:0 4px 16px rgba(0,0,0,.22);color:#fff;background:#2A285F}" +
      ".rasoff.off{background:#9B1C1C}.rasoff.env{background:#1B5173}.rasoff.ok{background:#2F6B3B}" +
      ".rasoff b{font-weight:800}.rasoff .dot{width:9px;height:9px;border-radius:50%;background:currentColor;flex:none;opacity:.9}" +
      ".rasoff button{appearance:none;border:1px solid rgba(255,255,255,.55);background:transparent;color:#fff;" +
      "font:inherit;padding:3px 9px;border-radius:8px;cursor:pointer}";
    document.head.appendChild(st);
    _el = document.createElement("div");
    _el.className = "rasoff";
    document.body.appendChild(_el);
    return _el;
  }
  function pintar(){
    const e = el(); if(!e) return;
    const n = pendentes();
    const off = navigator.onLine === false;
    const plural = n === 1 ? "alteração" : "alterações";
    if(off){
      e.className = "rasoff off";
      e.innerHTML = n
        ? `<span class="dot"></span><span><b>Sem internet</b> · ${n} ${plural} guardada${n===1?"":"s"} neste aparelho — envio automático quando a conexão voltar</span>`
        : `<span class="dot"></span><span><b>Sem internet</b> · pode continuar preenchendo: fica guardado neste aparelho</span>`;
      e.style.display = "flex";
    } else if(n){
      e.className = "rasoff env";
      e.innerHTML = `<span class="dot"></span><span>${_drenando ? "Enviando" : "Aguardando envio de"} <b>${n}</b> ${plural} ao Notion…</span>` +
                    (_drenando ? "" : `<button type="button" onclick="RasOffline.drenar()">enviar agora</button>`);
      e.style.display = "flex";
    } else if(_tinha){
      e.className = "rasoff ok";
      e.innerHTML = `<span class="dot"></span><span>Tudo enviado ao Notion ✓</span>`;
      e.style.display = "flex";
      clearTimeout(_okT); _okT = setTimeout(() => { if(!pendentes() && navigator.onLine !== false) e.style.display = "none"; }, 3500);
    } else {
      e.style.display = "none";
    }
    _tinha = n;
  }

  /* Texto para os avisos da página ("... no Notion." vs guardado no aparelho) */
  function onde(){
    return navigator.onLine === false
      ? " — guardada neste aparelho; vai para o Notion quando a internet voltar."
      : " no Notion.";
  }

  /* ---------------- gatilhos ---------------- */
  function tentar(){ if(pendentes()) drenar(); else pintar(); }
  window.addEventListener("online",  () => { pintar(); drenar(); });
  window.addEventListener("offline", pintar);
  window.addEventListener("load",    tentar);
  document.addEventListener("visibilitychange", () => { if(!document.hidden) tentar(); });
  /* Outra aba da mesma RAS mexeu na fila: atualiza a faixa desta */
  window.addEventListener("storage", ev => { if(ev.key === CHAVE) pintar(); });
  setInterval(tentar, INTERVALO);
  if(document.readyState !== "loading") setTimeout(tentar, 0);
  else document.addEventListener("DOMContentLoaded", tentar);

  /* ---------------- service worker: abre o site sem internet ---------------- */
  if("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")){
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("sw.js").catch(e => console.warn("[ras-offline] sw.js não registrou", e));
    });
  }

  window.RasOffline = { enviar, drenar, aplicar, estado, editarCriacao, cancelarCriacao, pendentes, onde };
})();
