# Painel de Ingressos - Londrisoft Camp 2026

Documento de projeto para execução em gates pelo Claude Code. Cada gate é um
prompt. Não avançar para o próximo sem o critério de aceite cumprido.

## 1. Contexto

Os ingressos do Londrisoft Camp 2026 são vendidos pela Luma. Existe uma meta
de Fase 1 que se encerra em 15/10/2026, e o evento acontece em 11/11/2026.

Dois times competem em metas separadas, meta consolidada do painel é
**400** (300 CSM + 100 Comercial):

| Time | Meta total | Distribuição | Quebra individual na TV? |
|---|---|---|---|
| CSM | 300 | 4 gerentes de conta, 75 cada (Lucineia, Gian, Pati, Gui) | Sim |
| Comercial | 100 | 3 vendedores com 30 cada (Clayton, Antonio, Adriano), mais 10 do gerente (Raul) | Não — meta coletiva só |

O Marketing tem 100 ingressos próprios, mas fica **fora do painel por
enquanto**. A tela Geral mostra 400 como total consolidado, sem nenhuma
referência ao 500 (400 + Marketing).

Só o CSM mantém quebra individual por gerente no card "Por gerente" — é o
desenho original que já existia no front. O Comercial é meta coletiva na
TV, sem card individual (decisão revertida em relação a uma versão anterior
deste documento, que pedia o mesmo card pro Comercial — não pedir mais).
Isso não significa que a venda de cada vendedor do Comercial deixa de ser
rastreada: os 4 utm_source continuam sendo atribuídos normalmente por
baixo dos panos, só não aparecem quebrados na TV — ficam visíveis na tela
de admin.

**Maria não é vendedora.** Não tem meta, não entra em `vendedor`, e
qualquer venda que por acaso apontar pra ela (utm_source ou cupom) deve
cair em sem atribuição, não ser interpretada como dela.

O painel roda numa TV, em rotação automática de três telas a cada 2 minutos.
É um painel geral da empresa, não restrito ao time comercial.

Substitui um fluxo atual em Make, que ficou complexo demais para manter.

## 2. Decisões já travadas

- Atribuição de venda por dois sinais, em ordem de precedência: correção
  manual (se existir) primeiro, depois **utm_source do link** como sinal
  principal (cada vendedor tem um link próprio, gerado e distribuído
  centralmente pela Mariana), e **cupom** como sinal secundário, resolvido
  por uma tabela de mapeamento explícita `cupom_codigo → vendedor` — nunca
  por regex sobre o texto do código (o cupom real `LUVIP`, da Lucineia, não
  segue nenhum padrão de nome+número). Sem match em nenhum dos dois, cai na
  fila de sem atribuição. Ver seção 6.
- **Sem venda manual.** Toda venda vem da Luma. Não existe lançamento
  manual, não existe conciliação por e-mail, não existe risco de contagem
  dupla entre fontes.
- **O painel não lida com dinheiro.** Nenhuma tela — nem a TV pública, nem a
  tela de correção — mostra faturamento, calcula bônus, ou armazena valor em
  centavos. Ingresso reembolsado ou não capturado (`is_captured: false`)
  continua excluído da contagem de vendidos, mas por uma flag de validade,
  não por um valor monetário guardado ou somado.
- O dado bruto da Luma nunca é sobrescrito. Correções vivem numa camada
  separada e são resolvidas na leitura. Nenhum resync apaga uma correção
  manual.
- Sem Google Sheets no meio do pipeline. A correção de atribuição é feita
  numa tela administrativa protegida por senha, gravando no próprio
  Postgres, com autoria e motivo registrados.
- Sync fora do Render. Render Free não tem cron job nem background worker, e
  a cota de 750 horas de instância é por workspace. O sync roda em GitHub
  Actions e escreve direto no Neon. O serviço no Render só lê do banco.
- Conta Render separada, não a conta principal que já hospeda
  dashboard-moskit, copiloto-comercial e ollow-exporter.
- Banco no Neon, nunca o Postgres free do Render, que expira 30 dias após a
  criação.

## 3. Decisões resolvidas

As 5 decisões que bloqueavam o Gate 1 foram fechadas:

1. **Luma Plus está ativo?** Sim — confirmado no Gate 1 com chamada real.
2. **CSM e Comercial em calendários diferentes?** Não. Confirmado no Gate 1:
   é um único evento (`evt-59xGdD8EixaTOAa`), um único calendário. O sync
   usa uma chave só, sem loop.
3. **Venda manual conta pra meta?** Decisão mudou o escopo: **não existe
   mais venda manual**. Toda venda vem da Luma (ver seção 2).
4. **CSM usa cupom ou só link?** Os dois times agora usam a mesma regra:
   utm_source é o sinal principal, cupom é secundário via tabela de
   mapeamento (não regex). Ver seção 6.
5. **De onde vem a meta acumulada por semana?** Tabela `meta_semanal`,
   editável por dado — não fixa em código.

**Fechado:** Fase 1 vai de 31/08/2026 a 15/10/2026 — 32 dias úteis, 7
semanas. `config.fase1_inicio` = 2026-08-31. As três datas
(`fase1_inicio`, `fase1_fim`, `data_evento`) estão gravadas — ver seção 5.

A meta acumulada semanal (`meta_semanal`) também mudou de valor: os números
que o Gate 2 semeou (105/150/190/225/255/280/300 pro CSM,
40/55/68/79/88/95/100 pro Comercial) eram provisórios. Os reais, com o
calendário de dias úteis considerando os feriados de 07/09 e 12/10, estão
na tabela da seção 5. Como o Gate 2 já tinha rodado contra o Neon, a
correção entrou como uma migration nova (`004`), não editando a `002` já
aplicada — nunca se edita uma migration depois que ela rodou de verdade.

## 4. Arquitetura

```
GitHub Actions (cron 15 min)
        |
        v
  sync/run.py  -->  API Luma (public-api.luma.com)
        |
        v
   Neon Postgres  <--  admin (correções manuais)
        |
        v
  FastAPI no Render (só leitura)
        |
        v
   TV (index.html)
```

Stack: Python 3.12, FastAPI, uvicorn, psycopg 3, httpx. Sem ORM. SQL puro em
arquivos versionados. Front estático servido pelo próprio FastAPI.

Estrutura de pastas:

```
/app
  main.py            FastAPI, rotas públicas e admin
  db.py              pool de conexão psycopg
  painel.py          monta o payload do painel
  admin.py           rotas de correção
/sync
  run.py             entrypoint do cron
  luma.py            client da API Luma
  (a resolução de atribuição vive na view v_ingresso_atribuido, em SQL —
   não tem atribuicao.py separado)
/migrations
  001_raw.sql
  002_negocio.sql
  003_views.sql
/static
  index.html
  /assets
/.github/workflows/sync.yml
```

## 5. Modelo de dados

Sem venda manual e sem valor monetário em nenhuma tabela — o painel só
conta ingressos. Se algum dia precisar do valor pago, ele ainda existe
dentro do `raw jsonb`, só não vira coluna de primeira classe.

### Camada bruta (espelho da Luma, nunca editada à mão)

```
luma_event    (id, nome, calendario_id, inicio_em, raw jsonb, sincronizado_em)

luma_guest    (id, event_id, nome, email, status, utm_source,
               registrado_em, raw jsonb, sincronizado_em)

luma_ticket   (id, guest_id, event_id, ticket_type_id, ticket_type_nome,
               cupom_codigo, valido bool, checked_in bool, criado_em,
               raw jsonb, sincronizado_em)

sync_run      (id, iniciado_em, terminado_em, tipo, guests_lidos,
               tickets_lidos, erros, detalhe jsonb)
```

`raw jsonb` guarda a resposta original de cada objeto. Serve para
reprocessar sem bater na API de novo quando uma regra de negócio mudar — e
é onde o valor pago mora, caso um dia seja preciso.

`valido` cobre **só** reembolso e cancelamento. Não cobre mais captura —
decisão da Mariana que substitui a regra original do Gate 1: ingresso
grátis intencional conta igual a pago, `is_captured: false` deixou de ser
critério de exclusão. Quem decide se um ingresso aparece no painel agora é
a atribuição (ver seção 6), não este booleano sozinho. O registro nunca é
deletado, só marcado.

### Camada de negócio (editável)

```
vendedor              (id, nome, utm_source, time, meta, ativo)
                       time em ('csm', 'comercial')
                       nome = exibido na TV; utm_source = marcador do link,
                       de propósito diferentes um do outro

cupom_vendedor         (cupom_codigo, vendedor_id nullable, observacao, criado_em)
                       mapeamento explícito, não regex. vendedor_id nulo é um
                       cupom conhecido sem vendedor ativo (caso real: RAFA50)

atribuicao_override   (ticket_id, vendedor_id, motivo, autor, criado_em)

meta_semanal          (time, semana, meta_acumulada)

config                (chave, valor)
                       fase1_inicio, fase1_fim, data_evento, fonte_label
```

`meta_semanal`, valores reais (migration `004`), Fase 1 de 31/08 a
15/10/2026, 7 semanas, considerando os feriados de 07/09 e 12/10:

| Semana | Período | Dias úteis | CSM acum. | Comercial acum. |
|---|---|---|---|---|
| S1 | 31/08–04/09 | 5 | 28 | 9 |
| S2 | 07–11/09 | 4 | 68 | 22 |
| S3 | 14–18/09 | 5 | 116 | 38 |
| S4 | 21–25/09 | 5 | 168 | 55 |
| S5 | 28/09–02/10 | 5 | 220 | 72 |
| S6 | 05–09/10 | 5 | 272 | 89 |
| S7 | 12–15/10 | 3 | 300 | 100 |

A meta individual acumulada por gerente do CSM (7, 17, 29, 42, 55, 68, 75)
é exatamente a meta do time dividida por 4 — confirmado, os 4 gerentes têm
meta igual (75 cada) e a rampa é distribuída igual entre eles. Não virou
tabela própria: o front não usa ritmo semanal por pessoa hoje (só o
agregado do time), e o número é derivável a qualquer momento
(`meta_semanal.meta_acumulada / 4`). Se um dia precisar de verdade, é uma
migration nova, não uma suposição no meio do código.

`config`, valores reais (migration `004`):

| chave | valor |
|---|---|
| `fase1_inicio` | `2026-08-31` |
| `fase1_fim` | `2026-10-15` |
| `data_evento` | `2026-11-11` |
| `fonte_label` | `Luma` |

## 6. Regra de atribuição

Resolvida numa view, na leitura, nesta ordem de precedência (invertida em
relação à primeira versão do documento — link é o sinal principal agora):

1. `atribuicao_override.vendedor_id`, se existir para aquele ticket
2. `luma_guest.utm_source`, casando com `vendedor.utm_source` — comparação
   **normalizada** (`lower(trim(...))` dos dois lados) para tolerar
   variação de digitação e maiúscula/minúscula. Confirmado: o utm_source
   real chega capitalizado da Luma (`"Lucineia"`, `"Guilherme"`), e às
   vezes não é vendedor nenhum, é canal de divulgação (`"Instagram"`). Só
   bate se o valor normalizado for **exatamente igual** ao de algum dos 8
   vendedores ativos — `"Instagram"` nunca vira atribuição, cai direto pra
   sem atribuição. Vazio (`''` ou só espaço) conta como ausente, igual a
   nulo.
3. `luma_ticket.cupom_codigo`, casando com `cupom_vendedor.cupom_codigo` —
   mapeamento explícito, gravado à mão, nunca extraído do texto do código
   por regex. Um cupom pode estar na tabela e ainda assim não resolver
   ninguém, se `vendedor_id` estiver nulo (ver seção 5) ou se o vendedor
   mapeado estiver `ativo = false`.
4. sem atribuição — cai na fila de revisão

O valor bruto do `utm_source` nunca é normalizado na origem —
`luma_guest.utm_source` guarda exatamente o que a Luma devolveu, sem
sobrescrever. A normalização só acontece na comparação, dentro da view, que
expõe as duas versões lado a lado (a bruta e a normalizada) — assim quem
revisa a fila de sem atribuição vê o valor original, não só "sem
atribuição" sem contexto.

A view `v_ingresso_atribuido` expõe:

```
ticket_id, vendedor_id, time, valido, cupom_codigo,
utm_source_bruto, utm_source_normalizado, criado_em, atribuido_por,
conta_no_painel
```

`atribuido_por` guarda qual dos três níveis resolveu aquele ticket (ou
`sem_atribuicao`). É o que permite auditar depois quantas vendas vieram de
link e quantas de cupom.

**`conta_no_painel`** (decisão da Mariana, migration `006`, substitui a
regra do Gate 1): `valido AND vendedor_id is not null`. É esse booleano, e
não `valido` sozinho, que decide o que soma no total do time, na tela
Geral e no card individual. Um ingresso pode estar `valido = true` (não
reembolsado, não cancelado) e ainda assim `conta_no_painel = false`, se não
tiver atribuição nenhuma — continua gravado, continua aparecendo na view e
na fila de revisão, só não entra em nenhuma soma exibida. `is_captured` não
participa de nada disso — ingresso grátis intencional conta igual a pago,
desde que tenha atribuição.

Um cupom pode existir na tabela `cupom_vendedor` e o ingresso ainda cair em
`sem_atribuicao`/`conta_no_painel = false`, em dois casos reais: o cupom
está mapeado pra `vendedor_id` nulo de propósito (caso `RAFA50`), ou o
cupom nem está na tabela ainda. `RAFA50` (Rafael) segue sem vendedor de
propósito; `CLAYTON50` → Clayton e `PREMIUMIWA` → Guilherme foram os dois
cupons reais achados em uso no evento e mapeados por instrução explícita
depois (migrations `005` e `007`).

Não existe mais união com uma segunda origem — sem venda manual, todo
ticket vem da Luma, e a coluna `origem` que existia na primeira versão do
documento foi removida por não ter mais utilidade.

## 7. Contrato da API do painel

`GET /api/painel` devolve exatamente o shape do `DADO_PADRAO` do HTML
atual, mais os campos novos. O front não muda de estrutura, só troca a URL
do fetch.

Exemplo real, devolvido pela rota em 02/09/2026:

```json
{
  "fonte": "Luma",
  "atualizadoEm": "02/09/2026 09:54",
  "semAtribuicao": 9,
  "diasUteisRestantes": 30,
  "csm": {
    "meta": 300,
    "realizado": 5,
    "semanaAtual": 1,
    "metaSemana": 28,
    "realizadoSemana": 5,
    "metaAcumulada": [28, 68, 116, 168, 220, 272, 300],
    "realizadoAcumulado": [5, null, null, null, null, null, null],
    "ritmoNecessario": 10,
    "diferencaSemana": -23,
    "statusSemana": "atrasado",
    "gerentes": [
      { "nome": "Lucineia", "meta": 75, "realizado": 3 },
      { "nome": "Gian", "meta": 75, "realizado": 0 },
      { "nome": "Pati", "meta": 75, "realizado": 0 },
      { "nome": "Gui", "meta": 75, "realizado": 2 }
    ]
  },
  "comercial": {
    "meta": 100,
    "realizado": 1,
    "semanaAtual": 1,
    "metaSemana": 9,
    "realizadoSemana": 1,
    "metaAcumulada": [9, 22, 38, 55, 72, 89, 100],
    "realizadoAcumulado": [1, null, null, null, null, null, null],
    "ritmoNecessario": 4,
    "diferencaSemana": -8,
    "statusSemana": "atrasado"
  }
}
```

`diasUteisRestantes` é um número só, no topo — mesmo raciocínio do
`semAtribuicao`: a janela da Fase 1 é uma só, não faz sentido duplicar por
time. `ritmoNecessario`, `diferencaSemana` e `statusSemana` são por time,
calculados no backend (`app/painel.py`), nunca no front.

`semAtribuicao` é um número só, no topo — não existe por time. Um ingresso
sem atribuição não tem vendedor, e por isso não tem `time`: não tem como
saber se seria do CSM ou do Comercial sem inventar o dado.

`gerentes` só existe no `csm` — é o que já era o card "Por gerente" no
front original. O `comercial` não manda mais `gerentes`: a meta dele é
coletiva na TV (decisão revertida, ver seção 1), o front do painel
Comercial não muda. A quebra por vendedor do Comercial continua existindo
no banco (a view resolve por pessoa igual), só não é exposta nesta rota —
fica disponível pra tela de admin via consulta direta, não pelo contrato
público do painel.

Nenhum valor monetário entra nesta rota, nem em nenhuma outra — não existe
mais rota financeira. O painel da TV é público e mostra só contagem de
ingressos.

Demais rotas:

```
GET  /healthz
GET  /admin                      tela de correção (HTTP Basic)
GET  /api/admin/pendencias       tickets sem atribuição
POST /api/admin/override         grava atribuição manual de um ticket
```

## 8. Gates de execução

### Gate 0 - Esqueleto do repositório

Criar a estrutura de pastas, `pyproject.toml`, `.env.example`, `.gitignore`
e um `README.md` curto. Nenhuma lógica de negócio ainda.

`.env.example` deve listar: `LUMA_API_KEY`, `LUMA_CALENDAR_ID`,
`DATABASE_URL`, `DATABASE_URL_POOLED`, `ADMIN_USER`, `ADMIN_PASSWORD`,
`TZ=America/Sao_Paulo`.

O Neon expõe duas connection strings. `DATABASE_URL` é a conexão direta,
sem PgBouncer — usada por processos de vida curta que abrem uma conexão,
trabalham alguns minutos e terminam: o runner de migrations
(`scripts/migrate.py`) e o sync do GitHub Actions (Gate 4).
`DATABASE_URL_POOLED` passa pelo PgBouncer do Neon — usada pela API do
painel no Render (Gate 6), que fica no ar o tempo todo e mantém pool
próprio de conexões; ir direto arriscaria estourar o limite de conexões
simultâneas do Neon num plano gratuito.

**Aceite:** `uvicorn app.main:app` sobe e `/healthz` responde 200.
**Não fazer:** não criar migrations, não escrever client da Luma.

### Gate 1 - Diagnóstico da API Luma (read-only)

Script isolado `scripts/diagnostico_luma.py` que:

- lista os eventos do calendário
- chama `GET /v1/events/guests/list` num evento real e imprime o JSON de um
  guest
- pega o id desse guest e chama `GET /v1/events/guests/get`, imprimindo o
  objeto completo com `event_ticket_orders`
- salva as duas respostas cruas em `scripts/amostras/` para consulta

O objetivo é ver com os próprios olhos onde ficam, na resposta real: o valor
pago, o código do cupom, o valor do desconto, o utm_source, e o marcador de
reembolso ou cancelamento.

**Aceite:** as amostras estão salvas e os cinco campos acima estão
localizados e documentados no README, com o caminho exato dentro do JSON.
**Não fazer:** não modelar tabela nenhuma antes disso. O schema sai da
amostra real, não da suposição.

### Gate 2 - Migrations

Escrever `001_raw.sql`, `002_negocio.sql` e `003_views.sql` conforme a
seção 5, ajustados ao que o Gate 1 revelou. Runner simples em
`scripts/migrate.py` que aplica os arquivos em ordem e registra o que já
rodou numa tabela `schema_migration`.

Seed inicial: os 8 vendedores (4 CSM, 4 Comercial) com nome de exibição,
utm_source e meta, mais o mapeamento inicial de `cupom_vendedor` (LUVIP →
Lucineia, RAFA50 → sem vendedor ativo), as linhas de `config` e
`meta_semanal`.

**Aceite:** migrations aplicam num banco vazio e são idempotentes numa
segunda execução.
**Não fazer:** não usar ORM, não gerar migration automática.

**Atualização pós-execução:** `004_ajustes_fase1.sql` corrigiu os valores
provisórios de `meta_semanal` para os reais (seção 5) e gravou
`config.fase1_inicio`, depois que a Fase 1 e o calendário de dias úteis
foram fechados — o Gate 2 original já tinha rodado contra o Neon, então a
correção virou migration nova, não edição da `002` já aplicada.

### Gate 3 - Client da Luma

`sync/luma.py` com paginação completa, header `x-luma-api-key`, timeout,
retry com backoff em 429 e em 5xx. O limite é de 200 requisições por minuto
por calendário.

Como `guests/list` não traz detalhe de pedido, o detalhe de cupom exige uma
chamada por guest em `guests/get`. Implementar isso com controle de taxa e
pulando guests que já estão em dia (comparação por `updated_at` ou hash do
raw).

**Aceite:** teste que simula 429 e confirma o backoff. Roda contra o
calendário real sem estourar o limite.
**Não fazer:** não gravar em banco ainda, o client só devolve objetos.

**Atualização pós-execução:** ritmo fixado em ~150 req/min (abaixo do teto
de 200), paginação confia só em `has_more`. 7 testes cobrindo backoff em
429 (respeitando `Retry-After`) e 5xx, esgotamento de tentativas,
paginação, e erro 403 real (evento sem acesso) propagado sem contorno.
Rodou contra a API real: 9 eventos, 17 guests do Camp, detalhe de 3 guests
via `guests/get`, sem 429.

### Gate 4 - Sync

`sync/run.py` com dois modos:

- `--incremental` (padrão do cron): só guests novos ou alterados
- `--full`: varre tudo e reconcilia, marcando como `valido = false` o que
  sumiu ou foi reembolsado

Toda execução grava uma linha em `sync_run`. Upsert por id, nunca delete.

**Aceite:** rodar incremental duas vezes seguidas não duplica nada. Rodar
full depois de um reembolso na Luma marca o ticket como inválido e o total
do painel cai.
**Não fazer:** não tocar em `atribuicao_override`, em nenhum dos dois modos.

**Atualização pós-execução:** `criado_em` do ticket usa `registered_at` do
guest — a Luma não expõe uma data de criação própria do ticket/pedido.
Rodou contra o Camp real: incremental duas vezes seguidas (a segunda não
reprocessou nenhum ticket, confirmando que a checagem de mudança funciona)
e uma vez `--full` (reprocessou todos, 0 invalidados por reconciliação —
nada sumiu entre as execuções). Não foi possível testar o caminho
"reembolso real" ponta a ponta sem reembolsar um ingresso de verdade na
Luma de produção — a lógica foi validada por teste unitário
(`test_sync_regras.py`), não por reembolso real.

`valido` originalmente também derivava de `is_captured` — regra revista
depois da primeira rodada real: 5 dos 15 ingressos vieram de tipos de
ingresso configurados como grátis de propósito na própria Luma (`type:
"free"` em `/v1/events/ticket-types/list`, endpoint novo, não estava no
Gate 1), não convite pendente. A Mariana decidiu que grátis intencional
conta igual a pago — `is_captured` saiu da equação, ver seção 6
(`conta_no_painel`) e migration `006`. `migrations/005` também mapeou o
cupom real `CLAYTON50` → Clayton, confirmado em uso no evento.

### Gate 5 - Atribuição

A view `v_ingresso_atribuido` já existe e já implementa a precedência da
seção 6, incluindo `conta_no_painel` (migration `006`). Este gate é sobre
provar isso com teste, contra dado real gravado no Neon — não escrever
`sync/atribuicao.py` como um módulo Python separado, já que a resolução
inteira vive na view em SQL.

Casos que os testes precisam cobrir: utm_source batendo, utm_source
capitalizado como vem da Luma (`"Lucineia"`) batendo depois de normalizar,
utm_source de canal que não é vendedor (`"Instagram"` — tem que cair em sem
atribuição, com o valor bruto visível, não silenciosamente ignorado),
utm_source vazio, cupom presente na tabela `cupom_vendedor` mas com
`vendedor_id` nulo (caso real: RAFA50 — tem que cair em sem atribuição, não
estourar erro), cupom presente e vendedor ativo (caso real: LUVIP →
Lucineia, CLAYTON50 → Clayton), cupom que não está na tabela nenhuma
(código fictício no teste — nunca usar cupom real aqui, porque cupom real
pode ganhar mapeamento numa migration futura, como aconteceu com
`PREMIUMIWA`), ticket sem cupom e sem utm_source, ticket com override
apontando para vendedor diferente do que o utm_source ou cupom indicariam
(override vence), ticket reembolsado (não conta mesmo com atribuição
resolvida), e ticket sem atribuição mas capturado/pago (`conta_no_painel`
tem que ser `false` mesmo `valido` sendo `true` — é a atribuição que
decide, não mais a captura).

**Aceite:** os onze casos acima cobertos por teste, e a view devolve
`atribuido_por` e `conta_no_painel` corretos em cada um.
**Não fazer:** não deixar a resolução silenciosamente ignorar um cupom que
não casou. Ele precisa cair em "sem atribuição" e aparecer na fila de
revisão. Não usar regex sobre o texto do cupom.

**Atualização pós-execução:** 12 testes em `tests/test_atribuicao_view.py`
(um dos onze casos parametrizado em dois — `LUVIP`→Lucineia e
`CLAYTON50`→Clayton), todos contra o Neon real, dado sintético inserido e
sempre revertido (`conn.rollback()`, nunca `commit()`) pra nunca poluir o
dado real do Camp. Confirmado depois de rodar: `luma_ticket`/`luma_guest`
continuam com as mesmas 15/17 linhas de antes do teste.

### Gate 6 - API do painel

`app/painel.py` montando o payload da seção 7, com `semanaAtual` derivada de
`config.fase1_inicio` no fuso America/Sao_Paulo.

**Aceite:** o JSON de `/api/painel` valida contra o shape do `DADO_PADRAO`,
chave por chave, incluindo `gerentes` só no CSM (Comercial não manda mais
esse campo — ver seção 7).
**Não fazer:** nenhum campo financeiro nesta rota.

**Atualização pós-execução (pedido depois do Gate 10):** a tela Geral
ganhou 3 informações por time — `ritmoNecessario` (ingressos por dia útil
pra fechar a meta até 15/10), `diferencaSemana` (realizado − meta da
semana atual) e `statusSemana` (`no_ritmo`/`atencao`/`atrasado`, ok/amber
acima de 80% da meta semanal, vermelho abaixo). `diasUteisRestantes` (topo
do payload, não por time — a janela da Fase 1 é uma só) exclui fim de
semana e os dois feriados que já valiam pra `meta_semanal` (07/09, 12/10).
Tudo calculado em `app/painel.py`, nada no front — o front só escolhe
cor/rótulo a partir de `statusSemana`.

**Atualização pós-execução:** `semAtribuicao` saiu do shape original — não
é mais um campo dentro de `csm`/`comercial`, é um número só no topo do
payload. Um ingresso sem atribuição não tem vendedor, e por isso não tem
`time` — não tinha como saber se seria do CSM ou do Comercial, então
dividir esse número por time seria inventar um dado que não existe. `meta`
de cada time também não é mais fixo (300/100 direto), é
`sum(vendedor.meta)` por time, calculado toda vez — mesma filosofia de não
fixar número em código que já valia pra `meta_semanal`. `app/db.py` criado
agora, usando `DATABASE_URL_POOLED` (decisão do Gate 0). Rodou contra o
Neon e a Luma reais — resultado na conversa. 1 teste de contrato
(`test_painel_route.py`) validando o shape e a ausência de qualquer termo
monetário no payload. 27 testes no total, todos passando.

### Gate 7 - Front

Mover o `index.html` real (já copiado em `/static`, ver README) pra ser
servido pelo FastAPI e fazer duas mudanças cirúrgicas no arquivo:

- trocar `fetch("data.json")` por `fetch("/api/painel")`, mantendo o
  fallback para `DADO_PADRAO` quando a rota falhar (é o que segura a TV
  numa queda do banco)
- adicionar um recarregamento periódico do payload, a cada 5 minutos, sem
  recarregar a página inteira

**Não criar mais o card "Por vendedor" no painel Comercial** — decisão
revertida (seção 1). O painel Comercial fica exatamente como já está hoje:
meta coletiva, sem quebra individual.

Se `semAtribuicao` for maior que zero, mostrar a contagem no rodapé. O que
não aparece na tela ninguém corrige.

**Aceite:** a TV mostra as três telas em rotação com dado real. O painel
Comercial continua sem quebra por pessoa.
**Não fazer:** não redesenhar o layout, não trocar a paleta, não mexer nas
fontes, não adicionar quebra individual no Comercial. A Stack Sans Notch
continua caindo no fallback até o arquivo ser fornecido.

**Atualização pós-execução:** `app/main.py` agora monta `StaticFiles` em
`/`, registrado depois das rotas de API — `/healthz` e `/api/painel`
continuam batendo primeiro, o mount só pega o resto (`/`, `/assets/...`).
`semAtribuicao` (número único, não por time — ver seção 7) aparece no
rodapé, cor de alerta funcional, escondido quando é zero. O recarregamento
periódico (5 min) só troca `dado` e re-renderiza se o fetch funcionar — uma
falha passageira não derruba a TV de volta pro `DADO_PADRAO` fictício,
mantém o último dado real na tela. Testado ao vivo: as três telas
(screenshot de cada uma), zero erro de console, servidor rodando contra o
Neon e a Luma reais.

### Gate 8 - Tela de correção

`/admin` protegida por HTTP Basic, com um bloco só:

- fila de pendências: tickets sem atribuição, com select de vendedor, campo
  de motivo e salvar

Sem lançamento de venda manual, sem tela financeira — esse escopo foi
removido do projeto.

Toda gravação registra autor e timestamp.

**Aceite:** correção feita na tela sobrevive a um `--full` logo em seguida.
**Não fazer:** não permitir edição de nada nas tabelas `luma_*`.

### Gate 9 - Cron no GitHub Actions

`.github/workflows/sync.yml` com schedule a cada 15 minutos rodando o
incremental, e um segundo schedule diário de madrugada rodando o full.
Segredos em GitHub Secrets. `workflow_dispatch` habilitado para disparo
manual.

**Aceite:** duas execuções verdes no Actions, com linha correspondente em
`sync_run`.
**Não fazer:** não colocar o sync dentro do processo do FastAPI.

**Execução:** `.github/workflows/sync.yml` criado, com os dois schedules
(incremental `*/15 * * * *`; full `0 6 * * *` = 03:00 America/Sao_Paulo,
sem DST) mais `workflow_dispatch` com escolha manual de modo. Distingue os
dois schedules por `github.event.schedule`, não por hora fixa em duplicado.
Precisa de dois GitHub Secrets no repositório — `LUMA_API_KEY` e
`DATABASE_URL` (a direta, não a pooled) — configurados por fora do chat.

### Gate 10 - Deploy

Executado fora de ordem, antes dos Gates 8 e 9 — a Mariana pediu pra tirar
a dependência da máquina local o quanto antes. Sync continua manual
(`python -m sync.run`) até o Gate 9 existir; o painel deployado mostra o
que já estiver gravado no Neon no momento.

Neon com o banco criado e migrations aplicadas. Render na conta nova, web
service free apontando para o repositório, variáveis de ambiente
configuradas.

Documentar no README que o serviço dorme após 15 minutos parado e leva cerca
de um minuto para acordar. Na prática, a TV ligada mantém o serviço acordado
sozinha, e o primeiro carregamento da manhã é lento uma vez só. Como o sync
roda fora do Render, nada é perdido enquanto o serviço dorme.

**Execução:** `render.yaml` na raiz do repo (Blueprint) define o web
service — build `pip install -e .`, start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check em
`/healthz`. Só uma variável de ambiente secreta: `DATABASE_URL_POOLED`
(marcada `sync: false` no blueprint — o Render pede o valor na hora do
deploy, direto no dashboard, nunca passa por aqui). `LUMA_API_KEY` e a
`DATABASE_URL` direta não entram no Render: o sync não roda lá, roda no
GitHub Actions (Gate 9) — o serviço no Render só lê.

**Aceite cumprido:** `https://painel-ingressos-camp-2026.onrender.com`
no ar, `/healthz` e `/api/painel` confirmados (curl direto, fora do
navegador) com dado real — 5/300 CSM, 1/100 Comercial, 9 sem atribuição,
`ritmoNecessario`/`diferencaSemana`/`statusSemana` também presentes.
Repositório na organização GitHub `Londrisoft-Camp`, deploy automático a
cada push confirmado (segundo commit, com os cards da tela Geral, subiu
sozinho sem precisar reconfigurar nada no Render).

## 9. Riscos conhecidos

- **Atribuição vaza.** O utm_source se perde quando alguém compartilha o
  link limpo, ou quando a pessoa volta pelo Google dias depois. Por isso os
  dois sinais convivem e a fila de correção fica visível na TV.
- **Cupom é imutável depois de criado.** Se alguém errar o desconto, precisa
  criar outro código — e como a atribuição por cupom agora é uma tabela de
  mapeamento manual, cada código novo precisa ser cadastrado em
  `cupom_vendedor` à mão, senão cai em sem atribuição.
- **Compra em grupo perde o cupom nos ingressos adicionais.** O cupom só se
  aplica no registro inicial. Um mesmo comprador gera ingresso com e sem
  atribuição.
- **Evento privado não rastreia referência.** Se a visibilidade do evento
  mudar para privado ou restrito a membros, o utm_source para de chegar e
  sobra só o cupom — que agora é o sinal secundário, então esse cenário
  aumenta a fila de sem atribuição.
- **Link é distribuído centralmente pela Mariana.** Como o utm_source virou
  o sinal principal, um vendedor divulgando o link errado (ou sem o
  parâmetro) some da atribuição até alguém notar pela fila de revisão.
- **Chave da Luma nunca vai para o front.** O painel lê do Postgres, jamais
  da Luma direto.
