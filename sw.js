/* Service worker — abre o site offline.
   dist/*.json NUNCA vai pro cache do SW: é o dado vivo, e o app.js já guarda
   a última cópia no localStorage. Cachear aqui mostraria dado velho pra sempre. */
const CACHE = "portal-morais-v3";
const ARQUIVOS = ["./","./index.html","./login.html","./vendas.html","./app.js","./manifest.json"];

self.addEventListener("install", e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ARQUIVOS)).then(()=>self.skipWaiting()));
});
self.addEventListener("activate", e=>{
  e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener("fetch", e=>{
  const req=e.request;
  if(req.method!=="GET") return;
  const url=new URL(req.url);
  if(url.origin!==self.location.origin) return;          // Apps Script, fontes: passa direto
  if(url.pathname.includes("/dist/")) return;            // dado vivo: sempre da rede
  // resto: rede primeiro, cache como rede de segurança
  e.respondWith(
    fetch(req).then(r=>{ const cp=r.clone(); caches.open(CACHE).then(c=>c.put(req,cp)); return r; })
              .catch(()=>caches.match(req).then(r=>r||caches.match("./index.html")))
  );
});
