-- Camada bruta: espelho da Luma, nunca editada à mão. Todo campo aqui
-- reflete literalmente o que a API devolve; correções de negócio vivem na
-- camada de negócio (002_negocio.sql), nunca aqui. O raw jsonb guarda a
-- resposta original de cada objeto, inclusive o valor pago — não existe
-- coluna de dinheiro nesta camada nem em nenhuma outra (ver seção 5 do
-- documento de projeto).

create table if not exists luma_event (
    id              text primary key,
    nome            text not null,
    calendario_id   text not null,
    inicio_em       timestamptz,
    raw             jsonb not null,
    sincronizado_em timestamptz not null default now()
);

create table if not exists luma_guest (
    id              text primary key,
    event_id        text not null references luma_event(id),
    nome            text,
    email           text,
    status          text,
    utm_source      text,
    registrado_em   timestamptz,
    raw             jsonb not null,
    sincronizado_em timestamptz not null default now()
);

create index if not exists idx_luma_guest_event_id on luma_guest(event_id);
create index if not exists idx_luma_guest_email on luma_guest(email);

-- valido cobre reembolso, cancelamento e ingresso não capturado
-- (is_captured: false na Luma) — achado real do Gate 1, um ticket não
-- capturado não é uma venda de verdade ainda. O registro nunca é deletado,
-- só marcado.
create table if not exists luma_ticket (
    id                text primary key,
    guest_id          text not null references luma_guest(id),
    event_id          text not null references luma_event(id),
    ticket_type_id    text,
    ticket_type_nome  text,
    cupom_codigo      text,
    valido            boolean not null default true,
    checked_in        boolean not null default false,
    criado_em         timestamptz,
    raw               jsonb not null,
    sincronizado_em   timestamptz not null default now()
);

create index if not exists idx_luma_ticket_guest_id on luma_ticket(guest_id);
create index if not exists idx_luma_ticket_event_id on luma_ticket(event_id);
create index if not exists idx_luma_ticket_cupom_codigo on luma_ticket(cupom_codigo);

create table if not exists sync_run (
    id            bigserial primary key,
    iniciado_em   timestamptz not null default now(),
    terminado_em  timestamptz,
    tipo          text not null check (tipo in ('incremental', 'full')),
    guests_lidos  integer not null default 0,
    tickets_lidos integer not null default 0,
    erros         integer not null default 0,
    detalhe       jsonb
);
