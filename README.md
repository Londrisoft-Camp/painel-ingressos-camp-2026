# Painel de Ingressos - Londrisoft Camp 2026

Painel de TV com o progresso de vendas de ingressos do Camp 2026, sincronizado a
partir da Luma. Substitui o fluxo anterior em Make.

Ver `projeto-painel-ingressos-camp-2026.md` (compartilhado pelo Raul) para o
documento de projeto completo, com arquitetura, modelo de dados e os gates de
execução.

## Rodando localmente

```
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload
```

`GET /healthz` responde 200 quando o serviço está de pé. `GET /` abre o
painel (a TV). `GET /api/painel` devolve só o JSON.

## Estrutura

- `app/` - FastAPI (rotas públicas e admin, só leitura em produção)
- `sync/` - sincronização com a Luma, roda fora do Render (GitHub Actions)
- `migrations/` - SQL puro, aplicado por `scripts/migrate.py`
- `static/` - front da TV (`index.html`)
- `scripts/` - utilitários (diagnóstico da API Luma, migrate)

## Status

- Gate 0 concluído: esqueleto do repositório.
- Gate 1 concluído: diagnóstico read-only da API Luma, com chamadas reais.
  Ver [`scripts/DIAGNOSTICO_LUMA.md`](scripts/DIAGNOSTICO_LUMA.md) para os
  endpoints reais, todos os campos documentados com tipo e caminho exato no
  JSON, o que a API não entrega, e o impacto nas decisões pendentes da
  seção 3 do documento de projeto. Amostras cruas em `scripts/amostras/`
  (fora do git).
- Gate 2 concluído: migrations aplicadas num Neon real
  (`python scripts/migrate.py`), confirmadas idempotentes rodando duas
  vezes seguidas. Tabelas de negócio (`vendedor`, `cupom_vendedor`,
  `meta_semanal`, `config`) semeadas com dado real. Sem `venda_manual`, sem
  coluna de dinheiro em nenhuma tabela — escopo removido do projeto.
  `004_ajustes_fase1.sql` corrigiu `meta_semanal` e `config.fase1_inicio`
  pros valores reais da Fase 1, depois de fechada.
- Gate 3 concluído: `sync/luma.py`, client HTTP puro (não grava em banco).
  7 testes (`pytest tests/`) cobrindo backoff em 429 e 5xx, esgotamento de
  tentativas, paginação que confia só em `has_more`, e erro real (403)
  propagado sem contorno. Rodou contra a API real (9 eventos, 17 guests do
  Camp, detalhe de 3 guests) sem erro de limite, paceado a ~150 req/min.
- Gate 4 concluído: `sync/run.py` (`--incremental` e `--full`), grava em
  `luma_event`/`luma_guest`/`luma_ticket`/`sync_run` no Neon. Rodou contra o
  Camp real duas vezes seguidas em incremental (segunda vez não reprocessa
  ninguém) e uma vez em `--full`. `valido` deriva só de reembolso e
  cancelamento (`is_captured` saiu da regra depois da primeira rodada real
  — ver Gate 5 e `migrations/006`).
- Gate 5 concluído: a atribuição inteira vive na view
  `v_ingresso_atribuido` (SQL, `003`/`006`) — sem `sync/atribuicao.py`
  separado. 12 testes (`test_atribuicao_view.py`) rodando contra o Neon
  real (dado sintético, sempre revertido, nunca fica gravado), cobrindo os
  11 casos da seção 8: override, utm_source (normal, capitalizado, canal
  não-vendedor, vazio), cupom (mapeado, sem vendedor ativo, não mapeado),
  sem atribuição nenhuma, e reembolsado. `conta_no_painel` é o booleano que
  o Gate 6 vai usar pra somar — só é `true` se `valido` **e** atribuído.
- Gate 6 concluído: `GET /api/painel` (`app/painel.py` + `app/db.py`, usa
  `DATABASE_URL_POOLED`). `semanaAtual` sempre calculada a partir de
  `config.fase1_inicio` contra a data de hoje (fuso America/Sao_Paulo),
  nunca fixada em código. `semAtribuicao` virou um número só, no topo do
  payload — ingresso sem atribuição não tem `time`, não dava pra separar
  por time sem inventar dado. Nenhum valor monetário em lugar nenhum
  (testado explicitamente). Rodou contra o Neon e a Luma reais — resultado
  real em 02/09/2026 na seção 7 do documento de projeto. 27 testes no
  total (`pytest tests/`), todos passando.
- Gate 7 concluído: `app/main.py` serve `static/` (mount depois das rotas
  de API, elas batem primeiro). Front trocou `data.json` por
  `/api/painel`, mantendo o fallback pro `DADO_PADRAO` só na carga inicial
  — uma falha no recarregamento periódico (5 min) não derruba a TV de
  volta pro dado fictício. `semAtribuicao` aparece no rodapé (cor de
  alerta, some se for zero). Testado ao vivo num browser de verdade
  (Playwright headless): as três telas com dado real, zero erro de
  console. Comercial confirmado sem card individual.

- Gate 10 concluído fora de ordem (a pedido da Mariana, antes dos Gates 8
  e 9). **No ar:** https://painel-ingressos-camp-2026.onrender.com —
  confirmado com curl direto (fora do navegador) em `/healthz` e
  `/api/painel`, dado real. Repositório na organização GitHub
  `Londrisoft-Camp`; deploy automático a cada push já confirmado (o
  segundo commit, com os cards da tela Geral, subiu sozinho).
- A tela Geral ganhou o que faltava: os cards de CSM e Comercial agora
  mostram ritmo necessário por dia útil (destaque, calculado no backend),
  comparação com a meta da semana (meta / realizado / diferença por
  extenso) e status colorido (verde/amarelo/vermelho — `no_ritmo` /
  `atencao` / `atrasado`, novos campos em `/api/painel`, nada calculado no
  front). Sem gráfico, sem lista de nomes nesse card — isso já existe nas
  outras duas telas.

Sem tela de correção ainda (Gate 8). Gate 9 (cron automático) em
andamento — ver abaixo. Até o cron rodar de verdade, o sync continua
manual (`python -m sync.run`).

## Automação (GitHub Actions — Gate 9)

`.github/workflows/sync.yml` roda `python -m sync.run` a cada 15 minutos
(incremental) e `--full` 1x por dia de madrugada (03:00 America/Sao_Paulo).
Também dá pra disparar manualmente pela aba **Actions** do GitHub
(`workflow_dispatch`, com escolha de modo).

Precisa de dois **GitHub Secrets** no repositório (Settings → Secrets and
variables → Actions → New repository secret), nunca colados no chat:

- `LUMA_API_KEY`
- `DATABASE_URL` — a direta, a mesma usada por `scripts/migrate.py`, não a
  pooled do Render.

## Deploy (Render)

`render.yaml` na raiz é um Blueprint do Render — ele lê esse arquivo e
configura o web service sozinho (build, start, health check). A única
variável de ambiente secreta que o serviço deployado precisa é
`DATABASE_URL_POOLED` — nem `LUMA_API_KEY` nem a `DATABASE_URL` direta vão
pro Render, porque o sync não roda lá (roda no GitHub Actions, Gate 9). O
Render pede o valor da `DATABASE_URL_POOLED` direto no dashboard dele, na
hora do deploy — nunca precisa passar pelo chat.

**O serviço free do Render dorme depois de 15 minutos sem requisição, e
leva cerca de 1 minuto pra acordar na próxima chamada.** Na prática, a TV
ligada o dia todo mantém o serviço acordado sozinha (ela bate na rota a
cada 5 minutos). O primeiro carregamento da manhã, ou depois de um período
longo sem acesso, é lento uma vez só — depois volta ao normal. Como o sync
roda fora do Render (GitHub Actions), nada é perdido enquanto o serviço
dorme: os dados continuam no Neon, só a resposta HTTP demora mais na
primeira chamada.

## Banco (Neon)

Duas connection strings, propósitos diferentes:

- `DATABASE_URL` — conexão direta, sem pooler. Usada por `scripts/migrate.py`
  e pelo sync (Gate 4): processos de vida curta, uma conexão só.
- `DATABASE_URL_POOLED` — via PgBouncer do Neon. Usada pela API do painel
  (`app/db.py`): processo que fica no ar o tempo todo.
