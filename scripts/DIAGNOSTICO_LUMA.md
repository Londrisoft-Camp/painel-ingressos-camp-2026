# Diagnóstico da API Luma - Gate 1

Read-only. Nenhuma tabela, nenhum schema, nenhum modelo de dados foi criado
neste gate. As chamadas foram feitas com a chave real fornecida, contra o
calendário de produção da Londrisoft, incluindo o evento real
**"Londrisoft Camp 2026"** (`evt-59xGdD8EixaTOAa`, 11/11/2026).

Amostras cruas em `scripts/amostras/` (fora do git):

- `events_list.json` — lista completa de eventos do calendário
- `guests_list_camp.json` — os 17 guests reais do evento do Camp
- `guests_get_camp.json` — detalhe completo de 5 guests do Camp (2 com
  cupom de 50%, 1 com cupom de 0%/VIP, 1 sem ticket, 1 sem captura)
- `guests_list.json` / `guest_get.json` — saída da execução automática de
  `scripts/diagnostico_luma.py` (mesmo evento e primeiro guest, gerado pelo
  script para servir de smoke test reproduzível)
- `erros.json` — três chamadas que falharam de propósito, com o erro cru

## 1. Endpoints que existem e funcionam

A documentação do projeto citava os paths com prefixo `/v1/events/...` para
listar eventos. **Isso está errado** — o path real, testado e funcionando, é:

| Endpoint | Método | Path real | Funciona? |
|---|---|---|---|
| Listar eventos do calendário | GET | `/v1/calendars/events/list` | Sim — HTTP 200 |
| Listar guests de um evento | GET | `/v1/events/guests/list?event_id=...` | Sim — HTTP 200 |
| Detalhe de um guest | GET | `/v1/events/guests/get?event_id=...&id=...` | Sim — HTTP 200 |

Autenticação: header `x-luma-api-key: <chave>` em todas as chamadas. Base
URL: `https://public-api.luma.com`.

`/v1/calendars/events/list` **não recebe `calendar_id` como parâmetro** — o
calendário é implícito na própria API key (cada key é presa a um
calendário). Isso muda a decisão pendente nº1 (ver seção 12).

## 2. O que veio no calendário

9 eventos no total, de reforma tributária a IA aplicada, todos no mesmo
`calendar_id` (`cal-oYZMAL1AmbE2TLD`), com um único evento correspondendo
ao Camp:

```
evt-59xGdD8EixaTOAa | "Londrisoft Camp 2026" | 11/11/2026
  visibility: public | registration_open: true | max_capacity: 1200
  spots_remaining: 1186 | display_price: {amount: 24700, currency: "brl"}
```

Existe também um evento anterior chamado "Lançamento Londrisoft Camp"
(`evt-GwllOF0OdUDRQOz`, 05/11/2025) — não confundir os dois. O evento com
os ingressos que o painel precisa contar é o `evt-59xGdD8EixaTOAa`.

**Achado importante:** só existe **um evento** de venda para o Camp 2026, e
portanto **um calendário só**. CSM e Comercial vendem para o mesmo
`event_id`. Isso elimina a hipótese de precisar de mais de uma
chave/calendário em loop — a não ser que decidam criar um segundo evento
Luma para separar os times, o que hoje não é o caso.

## 3. Campos por guest (`/v1/events/guests/list`)

Path no JSON: `body.entries[].*`

| Campo | Tipo | Nulo na prática? |
|---|---|---|
| `id` | string (`gst-...`) | não |
| `user_id` | string (`usr-...`) | não |
| `user_email` | string | não |
| `user_name` | string \| null | sim, um guest veio com `user_last_name: ""` |
| `user_first_name` / `user_last_name` | string \| null | last_name vazio em 1 caso |
| `approval_status` | enum: `approved`, `declined`, `pending_approval`, `waitlist`, `invited`, `session` | não |
| `check_in_qr_code` | string (URL) | não |
| `eth_address` / `solana_address` | string \| null | **sempre null** nos 17 |
| `invited_at` / `joined_at` | ISO datetime \| null | **sempre null** nos 17 |
| `phone_number` | string \| null | null em ~7 dos 17 (quem não preencheu WhatsApp) |
| `registered_at` | ISO datetime | não |
| `registration_answers` | array (perguntas custom do evento) | array vazio quando o guest ainda não respondeu (2 casos) |
| `utm_source` | string \| null | **null nos 17 guests reais**, ver seção 11 |
| `event_tickets` | array | array vazio quando o guest não tem nenhum ingresso associado (2 casos: guests recusados) |

Campo `event_tickets[]` (dentro do guest, mesmo endpoint):

| Campo | Tipo | Observação |
|---|---|---|
| `id` | string (`tkt-...`) | |
| `amount` | int (centavos) | **valor líquido pago**, não o de tabela — ver seção 5 |
| `amount_discount` | int (centavos) | valor abatido |
| `amount_tax` | int (centavos) | sempre `0` nos dados reais |
| `currency` | string | `"brl"` quando há cobrança real capturada; `"usd"` como placeholder quando `is_captured: false` (ver seção 7, é pegadinha) |
| `checked_in_at` | ISO datetime \| null | sempre null (evento ainda não aconteceu) |
| `event_ticket_type_id` | string (`ttype-...`) | identifica o lote/tipo (ex: "Premium Pass - 1° Lote", "Full Pass - VIP") |
| `is_captured` | bool | `false` = não é uma venda de verdade ainda (ver seção 7) |
| `name` | string | nome do tipo de ingresso |

**Não tem cupom aqui.** `event_tickets[]` não traz `cupom_codigo` nem
qualquer campo de desconto nomeado — só o valor já líquido.

## 4. Campos por pedido (`/v1/events/guests/get` → `event_ticket_orders[]`)

Path no JSON: `body.event_ticket_orders[].*`. Esse é o único lugar onde o
cupom aparece.

| Campo | Tipo | Observação |
|---|---|---|
| `id` | string (`tord-...`) | id do pedido, diferente do id do ticket |
| `amount` | int (centavos) | valor líquido pago |
| `amount_discount` | int (centavos) | valor abatido |
| `amount_tax` | int (centavos) | sempre `0` |
| `currency` | string | `"brl"` real ou `"usd"` placeholder (mesma pegadinha da seção 7) |
| `is_captured` | bool | |
| `amount_refunded` | int (centavos) | **é o marcador de reembolso.** `0` em todos os pedidos reais vistos — nenhum reembolso ocorreu ainda, então não dá pra confirmar visualmente como fica um valor >0, mas o campo existe e está documentado pela Luma como o valor devolvido |
| `coupon_info` | objeto \| **null** | só existe quando um cupom foi de fato aplicado |

`coupon_info` quando presente:

```json
{
  "api_id": "coup-7FY3AB659sLAEcv",
  "percent_off": 50,
  "cents_off": null,
  "currency": null,
  "code": "RAFA50"
}
```

`percent_off` e `cents_off` são mutuamente exclusivos (desconto percentual
ou em centavos fixos — nunca os dois). `code` é o texto do cupom.

**Não existe `approval_status` de cancelamento por ticket separado do
`approval_status` do guest** — reembolso/cancelamento hoje é inferido pela
combinação de `amount_refunded > 0`, `is_captured` e o `approval_status` do
guest (`declined`/`waitlist`), não por um campo booleano único
`valido`/`cancelado`.

## 5. Como valor pago e desconto realmente aparecem

Achado que muda a suposição do documento original: **`amount` já é o valor
líquido pago, não o valor de tabela.** O preço de tabela (o que o
formulário de checkout mostrou antes do cupom) é `amount + amount_discount`.

Exemplo real, cupom `RAFA50` (50% off) num "Premium Pass - 1° Lote":

```
amount:          19850   (R$ 198,50 — o que foi de fato cobrado)
amount_discount: 19850   (R$ 198,50 — o desconto)
preço de tabela = amount + amount_discount = 39700 (R$ 397,00)
```

Isso importa para a seção 5 do documento de projeto: `valor_bruto_cents`
em `luma_ticket` deve ser preenchido com `amount` (o que a Luma realmente
capturou), **não** `amount + amount_discount`. Faturamento bruto = soma de
`amount` dos tickets com `is_captured = true`, taxas da Luma/Stripe à parte
como já estava decidido.

## 6. Como o cupom aparece de fato (validação da convenção NOME+percentual)

Os cupons reais já em uso no calendário confirmam o padrão do documento,
mas com um contra-exemplo real que a regra de parsing precisa suportar:

| Código real | `percent_off` | Segue o padrão `NOME+número`? |
|---|---|---|
| `RAFA50` | 50 | sim |
| `CLAYTON50` | 50 | sim |
| `LUVIP` | 0 | **não** — sem dígitos, é um código de acesso VIP gratuito, não desconto percentual |

Recomendação para o Gate 5: usar a regex `^([A-Za-z]+)([0-9]{1,3})$` só
para **extrair o nome do vendedor** (prefixo de letras), e ler o percentual
de desconto do campo estruturado `coupon_info.percent_off` (ou
`cents_off`), em vez de parsear o número de dentro do código. Isso evita
quebrar em cupons como `LUVIP`, que não têm número — e o documento já prevê
que esse caso caia em "sem atribuição" (aqui, cairia porque a regex não
bate, então o comportamento esperado já está coberto, só a fonte do
percentual deve mudar).

## 7. Pegadinha: `is_captured: false` não é venda

Três dos 17 guests do Camp têm ticket com `amount: 0`, `currency: "usd"`,
`is_captured: false`, tipo "Full Pass - VIP" ou "Premium Pass - VIP". Não é
um ingresso brasileiro gratuito de fato — é um estado transitório (convite
pendente / captura de pagamento não efetivada) em que a Luma ainda não
processou uma moeda real, e devolve `"usd"` como valor padrão de sistema.

**Consequência para o Gate 4/Gate 6:** o sync e a contagem do painel devem
filtrar por `is_captured = true` para contar como venda. Contar
`event_tickets` sem esse filtro infla o número de ingressos vendidos.

## 8. Paginação

Confirmada nos dois endpoints de listagem (`events/list` e
`guests/list`), campos `has_more` (bool) e `next_cursor` (string, passado
de volta em `pagination_cursor` na próxima chamada).

**Quirk observado:** `next_cursor` vem preenchido mesmo quando
`has_more: false`. A implementação do Gate 3/4 deve confiar em `has_more`
para decidir se pagina de novo, e ignorar a mera presença de
`next_cursor`.

`pagination_limit` controla o tamanho da página (não testado no limite
máximo real, não documentado publicamente — vale testar no Gate 3 com um
valor alto e ver se a API recorta).

## 9. Limite de requisições

Confirmado nos headers de resposta, presentes em toda chamada autenticada:

```
x-ratelimit-limit: 200
x-ratelimit-remaining: <decrescente>
x-ratelimit-reset: <epoch>
```

200 requisições por minuto por calendário (API key de calendário), bloqueio
de 1 minuto e header `retry-after` ao estourar — bate exatamente com o que
o documento de projeto já assumia na seção do Gate 3.

## 10. Erros reais (não contornados)

| Caso | HTTP | Corpo |
|---|---|---|
| `event_id` inexistente ou de outro calendário | **403**, não 404 | `{"message":"You don't have access to this event.","code":null}` |
| `event_id` ausente (parâmetro obrigatório faltando) | 400 | `{"message":"Invalid request.\n- event_id: Invalid input: expected string, received undefined","code":null}` |
| API key inválida | 401 | `{"message":"You are not signed in.","code":null}` |

Ponto de atenção para o Gate 3: um `event_id` errado devolve **403**, não
**404** como seria intuitivo — o client e o handler de erro não podem tratar
403 genericamente como "sem permissão da chave", pode ser só um id que não
existe.

Não testei o 429 de propósito para não travar a chave de produção por 1
minuto sem necessidade — o comportamento documentado (`Retry-After` +
bloqueio de 60s) é o que o Gate 3 precisa implementar.

## 11. O que a API NÃO entrega (e o documento esperava)

- **Não existe um campo único "cancelado" ou "reembolsado" booleano por
  ticket.** O que existe é `amount_refunded` (valor, não flag) em
  `event_ticket_orders`, mais o `approval_status` do guest
  (`declined`/`waitlist`). O campo `valido` de `luma_ticket` (seção 5 do
  documento) vai ter que ser **derivado** na sincronização a partir desses
  dois sinais, não copiado direto de um campo da Luma.
- **Não existe `cupom_codigo` nem `desconto_cents` em `guests/list`.** Só
  aparece em `guests/get`, dentro de `event_ticket_orders[].coupon_info`.
  Isso confirma que o Gate 3 realmente precisa de uma chamada por guest
  (não dá pra economizar isso).
- **Não existe um campo de "valor de tabela" separado.** Só dá pra
  reconstruir com `amount + amount_discount` (seção 5 acima).
- **`utm_source` existe no schema mas está null em 100% dos guests reais
  do Camp hoje** (17 de 17). O mecanismo existe na API, mas ainda não há
  nenhuma prova real de captura funcionando — ninguém se cadastrou ainda
  usando um link com `?utm_source=`. Vale um teste manual antes do Gate 5:
  abrir `https://luma.com/bb8nunzg?utm_source=teste123`, se inscrever, e
  conferir se o `utm_source` aparece no guest correspondente.
- **Não existe endpoint de "listar cupons do evento"** nos dois endpoints
  testados — os únicos cupons visíveis são os que já foram usados em algum
  pedido. Não dá pra, via API, cruzar a lista de vendedores com a lista de
  cupons *criados* (só com os *usados*). Isso não bloqueia o projeto (a
  atribuição já é por matching, não por lista prévia), mas significa que
  não existe uma forma automática de detectar "vendedor cadastrado sem
  nenhum cupom criado ainda" — isso é operacional, fora do sistema.

## 12. Impacto nas decisões pendentes (seção 3 do documento de projeto)

1. **Luma Plus ativo?** Sim, confirmado — as três chamadas autenticadas
   retornaram 200 com dado real.
2. **CSM e Comercial em calendários diferentes?** Não. É o mesmo
   calendário e o mesmo evento (`evt-59xGdD8EixaTOAa`). Uma chave só
   resolve os dois times — não precisa de loop sobre lista de chaves, pelo
   menos com a configuração atual do evento.
3. **CSM usa cupom ou só link?** Não dá pra responder só com a API — os
   dois cupons reais achados (`RAFA50`, `CLAYTON50`) parecem ser do time
   Comercial. Continua sendo uma decisão de negócio, não técnica.
4. **Data de início da Fase 1 / meta semanal:** a API não tem opinião
   sobre isso, continua pendente de decisão humana.

Nenhuma dessas é bloqueante para os Gates 2-4 mudarem de plano — só a
correção de `valor_bruto_cents` (seção 5) e o filtro `is_captured` (seção
7) mudam o desenho original do schema/sync.
