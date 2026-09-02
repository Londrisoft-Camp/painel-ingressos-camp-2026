-- Camada de negócio: editável, nunca sobrescrita por sync. Vendedores,
-- mapeamento de cupom, correções manuais de atribuição, metas e config.
-- Sem venda_manual — esse escopo foi removido do projeto. Sem coluna de
-- dinheiro em lugar nenhum.

-- nome = exibido na TV; utm_source = marcador do link. De propósito
-- diferentes um do outro (ex: nome "Pati", utm_source "patricia").
create table if not exists vendedor (
    id          serial primary key,
    nome        text not null,
    utm_source  text not null,
    time        text not null check (time in ('csm', 'comercial')),
    meta        integer not null,
    ativo       boolean not null default true,
    criado_em   timestamptz not null default now(),
    unique (utm_source)
);

-- Mapeamento explícito cupom -> vendedor. Nunca regex sobre o texto do
-- código (ver seção 6 do documento: LUVIP não segue nenhum padrão de
-- nome+número). vendedor_id nulo é um cupom conhecido sem vendedor ativo
-- (caso real: RAFA50).
create table if not exists cupom_vendedor (
    cupom_codigo  text primary key,
    vendedor_id   integer references vendedor(id),
    observacao    text,
    criado_em     timestamptz not null default now()
);

create table if not exists atribuicao_override (
    ticket_id   text primary key references luma_ticket(id),
    vendedor_id integer not null references vendedor(id),
    motivo      text not null,
    autor       text not null,
    criado_em   timestamptz not null default now()
);

create table if not exists meta_semanal (
    time           text not null check (time in ('csm', 'comercial')),
    semana         integer not null check (semana between 1 and 7),
    meta_acumulada integer not null,
    primary key (time, semana)
);

create table if not exists config (
    chave text primary key,
    valor text not null
);

-- ---------------------------------------------------------------------
-- Seed: 8 vendedores (4 CSM, 4 Comercial)
-- ---------------------------------------------------------------------
insert into vendedor (nome, utm_source, time, meta) values
    ('Lucineia', 'lucineia',  'csm', 75),
    ('Gian',     'gian',      'csm', 75),
    ('Pati',     'patricia',  'csm', 75),
    ('Gui',      'guilherme', 'csm', 75),
    ('Raul',     'raul',      'comercial', 10),
    ('Clayton',  'clayton',   'comercial', 30),
    ('Antonio',  'antonio',   'comercial', 30),
    ('Adriano',  'adriano',   'comercial', 30)
on conflict (utm_source) do nothing;

-- ---------------------------------------------------------------------
-- Seed: mapeamento de cupom conhecido, achado real no Gate 1
-- ---------------------------------------------------------------------
insert into cupom_vendedor (cupom_codigo, vendedor_id, observacao)
select
    'LUVIP',
    id,
    'Cupom de acesso VIP da Lucineia. Achado real no Gate 1 (percent_off: 0), não segue o padrão nome+número.'
from vendedor
where utm_source = 'lucineia'
on conflict (cupom_codigo) do nothing;

insert into cupom_vendedor (cupom_codigo, vendedor_id, observacao) values
    (
        'RAFA50',
        null,
        'Cupom real achado no Gate 1 (percent_off: 50). Não corresponde a nenhum vendedor ativo da lista atual — caso de teste para "sem vendedor ativo".'
    )
on conflict (cupom_codigo) do nothing;

-- ---------------------------------------------------------------------
-- Seed: meta acumulada por semana (S1 a S7)
-- ---------------------------------------------------------------------
insert into meta_semanal (time, semana, meta_acumulada) values
    ('csm', 1, 105), ('csm', 2, 150), ('csm', 3, 190), ('csm', 4, 225),
    ('csm', 5, 255), ('csm', 6, 280), ('csm', 7, 300),
    ('comercial', 1, 40), ('comercial', 2, 55), ('comercial', 3, 68),
    ('comercial', 4, 79), ('comercial', 5, 88), ('comercial', 6, 95),
    ('comercial', 7, 100)
on conflict (time, semana) do nothing;

-- ---------------------------------------------------------------------
-- Seed: config. fase1_inicio fica de fora de propósito — data ainda não
-- foi definida (ver seção 3 do documento de projeto). Sem essa linha, o
-- Gate 6 não consegue derivar semanaAtual; não bloqueia este gate.
-- ---------------------------------------------------------------------
insert into config (chave, valor) values
    ('fase1_fim', '2026-10-15'),
    ('data_evento', '2026-11-11'),
    ('fonte_label', 'Luma')
on conflict (chave) do nothing;
