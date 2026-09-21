/* sw.js — RAS · Morais Engenharia  (IGUAL em todas as RAS)
 * ---------------------------------------------------------------------------
 * Faz a RAS ABRIR sem internet: guarda a página, o ras-offline.js e a última
 * cópia dos dados (dist/*.json).
 *
 * REDE PRIMEIRO, sempre: com internet, a tela recebe o arquivo novo e a cópia
 * guardada é atualizada. O cache só entra quando a rede falha — ou quando ela
 * demora mais de ESPERA ms (sinal fraco de obra), e aí a tela abre com a
 * última cópia em vez de ficar parada; o arquivo novo, se chegar, fica
 * guardado para a próxima vez.
 *
 * ORIGEM COMPARTILHADA: as RAS e o portal ficam todos em
 * devmoraiseng.github.io, e o "caches" é da origem inteira. Por isso:
 *   - o nome do cache leva a pasta deste site ("/RAS-SEMANAL/"), e
 *   - a limpeza de versões antigas só apaga caches DESTA pasta — nunca os das
 *     outras RAS nem o do portal.
 *
 * VERSAO: suba o número sempre que mudar ESTE arquivo ou a lista ARQUIVOS.
 * (index.html e ras-offline.js não precisam: são "rede primeiro", então quem
 * abre com internet já recebe a versão nova.)
 * ------------------------------------------------------------------------- */
const VERSAO = "v1";
const PASTA  = new URL(self.registration.scope).pathname;          // "/RAS-SEMANAL/"
const PREFIXO = "ras-cache::" + PASTA + "::";
const CACHE  = PREFIXO + VERSAO;
const ESPERA = 5000;

const ARQUIVOS = ["./", "./index.html", "./ras-offline.js"];
/* Nem toda RAS tem data_obras.json — cada um é tentado sozinho, e o que não
   existir é simplesmente ignorado (um addAll com um 404 derrubaria tudo). */
const DADOS = ["./dist/data_atividades.json", "./dist/data_obras.json"];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c =>
      c.addAll(ARQUIVOS).then(() => Promise.all(DADOS.map(u => c.add(u).catch(() => null))))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k.startsWith(PREFIXO) && k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if(req.method !== "GET") return;
  const url = new URL(req.url);
  if(url.origin !== self.location.origin) return;       // Apps Script, fontes do Google: direto
  if(!url.pathname.startsWith(PASTA)) return;           // outra RAS / portal: não é comigo
  e.respondWith(redePrimeiro(req));
});

function redePrimeiro(req){
  return caches.open(CACHE).then(c => new Promise((resolve, reject) => {
    let pronto = false;
    const entregar = r => { if(!pronto){ pronto = true; clearTimeout(t); resolve(r); } };
    const guardado = () => c.match(req, { ignoreSearch:true })
      .then(r => r || (req.mode === "navigate" ? c.match("./index.html") : null));

    const rede = fetch(req).then(r => {
      if(r && r.ok) c.put(req, r.clone()).catch(() => {});
      return r;
    });

    /* sinal fraco: passou do tempo e tem cópia guardada -> usa a cópia */
    const t = setTimeout(() => { guardado().then(g => { if(g) entregar(g); }); }, ESPERA);

    rede.then(entregar).catch(() =>
      guardado().then(g => {
        if(g) entregar(g);
        else if(!pronto){ pronto = true; clearTimeout(t); reject(new Error("offline e sem cópia")); }
      })
    );
  }));
}
