# PORTAL-MORAIS — o que configurar depois de subir estes arquivos

O site passou a ler **JSON estático** (`dist/`) em vez de chamar o Apps Script a
cada carregamento. É exatamente o que o RAS-SEMANAL faz, e é o motivo dele ser
rápido. O Apps Script continua sendo usado, mas só para **login e escrita**.

---

## 1. Configuração (só isso)

**Um único secret no GitHub** — `Settings > Secrets and variables > Actions`:

| Nome | Valor |
|---|---|
| `NOTION_TOKEN` | token da integração do Notion |

Os IDs das bases VENDAS e DOCUMENTOS já estão preenchidos no `fetch_vendas.py`
(IDs de base não são segredo — sem o token não abrem nada). Não precisa mexer
nisso.

**No Notion, compartilhar a base DOCUMENTOS com a integração** —
abrir a base > `...` > Conexões > adicionar a integração. A de VENDAS já deve
estar (o Apps Script usa), mas a de DOCUMENTOS provavelmente nunca foi. Sem isso
o Actions falha com 404.

**Rodar o workflow uma vez à mão:** `Actions > Publicar site > Run workflow`.

No log, confira: `colunas: endereço=... habite=... obra=...`. Se vier `None`,
me manda essa linha que eu ajusto a busca do nome.

## 1b. Fonte do Pages — SE ISTO ESTIVER ERRADO, NADA FUNCIONA

`Settings > Pages > Build and deployment > Source` tem que estar em
**GitHub Actions**. Se estiver em "Deploy from a branch", o GitHub roda **também**
o workflow próprio dele (`pages-build-deployment`, com Jekyll), que publica o
repositório como está commitado — **sem o `dist/`**, porque o `dist/` só nasce
durante o nosso build.

Os dois publicam o mesmo commit com segundos de diferença, e **o último ganha**.
Quando o do Jekyll chega por último, o site sobe sem `dist/` e mostra
"os dados ainda não foram publicados" — mesmo com o nosso workflow verde.

Como conferir: em `Actions`, se existir um workflow chamado
**pages-build-deployment** rodando junto do "Publicar site", é este o problema.
Trocar a Source para GitHub Actions desliga ele.

O arquivo `.nojekyll` na raiz é cinto de segurança: impede o Jekyll de mexer no
conteúdo caso ele rode de novo.

## 2. Com que frequência atualiza

Três gatilhos, todos já configurados em `.github/workflows/pages.yml`:

1. **A cada 15 min** (cron) — cobre edições feitas direto no Notion.
2. **A cada push** no `main`.
3. **`repository_dispatch`** do tipo `portal_update` — para o Apps Script
   disparar logo após uma escrita.

Ou seja: uma alteração feita **pelo site** aparece no site em ~2 min (tempo do
build) se você ligar o passo 3; uma alteração feita **direto no Notion** aparece
em até 15 min.

### Ligar o passo 3 no Apps Script

Adicione ao `Code.gs` e chame `agendarBuild()` no fim de cada escrita:

```javascript
var GH_REPO  = PropertiesService.getScriptProperties().getProperty('GITHUB_REPO');  // "DEVMoraisEng/PORTAL-MORAIS"
var GH_TOKEN = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN'); // PAT clássico, escopo "repo"

function agendarBuild() {
  if (!GH_REPO || !GH_TOKEN) return;
  UrlFetchApp.fetch('https://api.github.com/repos/' + GH_REPO + '/dispatches', {
    method: 'post',
    headers: {
      Authorization: 'Bearer ' + GH_TOKEN,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'
    },
    payload: JSON.stringify({ event_type: 'portal_update' }),
    muteHttpExceptions: true
  });
}
```

`GITHUB_REPO` tem que estar no formato `dono/repositório` — só o nome não funciona.

---

## 2b. Dados sensíveis não vão para o `dist/`

O `dist/` é servido pelo GitHub Pages **sem login** — quem souber a URL baixa o
arquivo. Deixar o repositório privado **não** muda isso (repositório privado e
site privado são coisas separadas; site privado de verdade só em Enterprise Cloud).

Por isso o `fetch_vendas.py` não publica as colunas pessoais. Como funciona:

1. No build, toda coluna cujo nome bata com `CAMPOS_SENSIVEIS` (topo do
   `fetch_vendas.py`) é marcada como `"sensivel": true` no `schema.json` e tem
   o **valor descartado** — não entra no `vendas.json`, nem vazio, nem mascarado.
2. Na planilha, essas colunas aparecem como `•••` e não são editáveis na célula.
3. Ao **abrir a obra**, o painel busca só esses campos no Apps Script, que
   confere o token da sessão antes de responder. Aí sim aparece o valor real e
   fica editável. Nada disso é guardado no cache do navegador.

Lista padrão (palavra inteira, tolerando plural, sem acento e sem caixa):
`CLIENTE, COMPRADOR, NOME DO CLIENTE, NOME DO COMPRADOR, CPF, CNPJ, RG,
IDENTIDADE, TELEFONE, CELULAR, WHATSAPP, CONTATO, E-MAIL, EMAIL, PARCELA,
FGTS, AGENCIA, CONTA CORRENTE, PIX, NASCIMENTO, ESTADO CIVIL, PROFISSAO,
RENDA, ENDERECO DO CLIENTE, ENDERECO RESIDENCIAL`

Além dessa lista, **toda coluna do tipo anexo (`files`) é oculta automaticamente**
(`OCULTAR_ANEXOS`). O Notion devolve URL assinada do S3: publicar isso no `dist/`
entregaria contrato e RG escaneado a quem tivesse o link do JSON, sem login.

Para mudar sem editar o código, defina a variável `CAMPOS_SENSIVEIS` no
workflow (separada por vírgula) — ela substitui a lista inteira.

**Confira no log do Actions** a linha `colunas NÃO publicadas em
dist/vendas.json`. Se alguma coluna que você queria esconder não estiver ali,
o nome real no Notion não bateu — me mande a linha que eu ajusto o fragmento.

### O que a planilha ainda mostra

Cada registro leva um resumo `sens` com **apenas "preenchido ou não"** (e, em
anexo, a quantidade). Nunca o conteúdo. Com isso a coluna oculta aparece como:

| Situação | Célula |
|---|---|
| Preenchido | `•••` |
| Anexo com 3 arquivos | `3 arq.` |
| Em branco | célula hachurada (dá pra ver o que falta preencher) |

É esse resumo que mantém o marcador de **obra vendida** funcionando mesmo com a
coluna `CLIENTES` oculta — o site pergunta "tem cliente?", não "quem é".

### Consequências esperadas

- A busca da planilha **não acha mais por cliente nem por CPF** (o dado não está
  no navegador). Passou a buscar por endereço, setor e cidade.
- As colunas ocultas **não são editáveis na célula** — só no painel da obra,
  depois que o valor real chega. Editar na célula sobrescreveria com vazio.
- Abrir a obra tem uma pequena espera nesses campos (`••• carregando…`), travados
  até o valor chegar.
- `VALOR NA MÃO` continua publicado: alimenta o marcador "disponível" e não é
  dado pessoal.

---

## 2c. Anexos e tema

- **Visualizar sem baixar:** PDF abre em iframe e imagem (jpg, png, webp, gif,
  bmp, avif) abre em `<img>` dentro do próprio site. `.docx` e `.zip` continuam
  só como link — navegador nenhum renderiza.
- **Nunca abre no escuro:** as três páginas trazem `color-scheme: light only`
  (meta + CSS) e o `manifest.json` tem fundo branco. Sem isso, o celular em modo
  escuro inverte os controles nativos (inputs, selects, seletor de data) e o
  formulário fica preto sobre layout claro.

---

## 2d. Ajustes por setor e página "Casas Modelo"

**Colunas escondidas em "Secretária de Vendas"** — lista `CAMPOS_OCULTOS_SETOR`
no `vendas.html`: `REF`, `CIDADE`, `SETOR`, `CASA` e o bloco de reparo
(`ANEXAR AQUIVO`, `ANEXAR ARQUIVO`, `REPARO`). O dado continua no registro — os
filtros de cidade/setor/casa seguem funcionando —, só não aparece na planilha
nem no painel **desse** setor. Para reverter, apague a linha correspondente.
A comparação é por palavra inteira: `CASA` não derruba `CASAS COMPORTADAS`, nem
`REF` derruba `REFORMA`.

**CLIENTES e CPF apareciam duas vezes** porque no Notion as colunas se chamam
`"CLIENTES "` e `"CPF "`, com espaço no fim: a comparação com a lista `RESUMO`
era por string crua e falhava, então o campo entrava no bloco de resumo **e** na
lista geral. Agora compara normalizado — vale para qualquer coluna com espaço
ou acento sobrando.

**Aba "Casas Modelo"** — nova página dentro do setor. Mostra só as obras com
`MODELO? = SIM` (aceita coluna do tipo select ou checkbox) e as colunas
`ENDEREÇO, CASA, MODELO?, TIPO, LOCALIZAÇÃO, LAYOUT, FOTOS`. Usa o mesmo
`vendas.json` já carregado — não faz requisição nova. `CASA` aparece aqui mesmo
estando oculta na Planilha do setor, porque foi pedida nesta lista.

`LAYOUT` e `FOTOS` são anexos: não vêm no `dist/` público. A célula mostra
`👁 N arq.` e abre a obra, onde os arquivos chegam pelo Apps Script.

---

## 3. O que o Apps Script ainda faz

- `login` / `me` — autenticação e sessão
- `updateVenda`, `baixa`, `upload`, `excluirVenda` — escrita
- `atividades` — lista de atividades em aberto (continua ao vivo, mas agora
  carrega em segundo plano: não segura mais a tela)
- `obra` — traz os campos sensíveis de UMA obra, sob demanda, quando o usuário
  logado abre o painel. É o único caminho para esses dados.

Os endpoints `vendas`, `vendasSchema` e `portal` **não são mais chamados** pelo
site. Pode deixá-los no `Code.gs` sem problema.

---

## 4. Arquivos de imagem

Continuam pendentes: `img/logo.png` e `img/gestores-vendas.jpg`.
Sem eles o site funciona (aparece "MORAIS" em texto no lugar da logo).

---

## 5. Usuários e senhas

Continua manual no banco **LOGINS** do Notion:

- **Novo usuário** — nova linha (LOGIN, SENHA, TIPO `ADM` ou `GERAL`, acessos).
- **Trocar senha** — editar a célula da senha no Notion.
- Na primeira entrada o `Code.gs` troca a senha em texto puro por um hash
  automaticamente. Para redefinir, é só escrever a senha nova em texto puro que
  o processo se repete.

Não existe tela de cadastro nem "esqueci minha senha" — se quiser, é a próxima
coisa que eu monto.
