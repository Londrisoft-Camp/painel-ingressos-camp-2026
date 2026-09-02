-- Resolve a atribuição na leitura, nesta ordem de precedência (seção 6 do
-- documento de projeto):
--   1. atribuicao_override, se existir
--   2. utm_source do guest, casando com vendedor.utm_source
--   3. cupom_codigo do ticket, casando com cupom_vendedor (mapeamento
--      explícito, nunca regex)
--   4. sem atribuição
--
-- utm_source chega da Luma capitalizado (ex: "Lucineia", "Guilherme") e às
-- vezes é um canal, não um vendedor (ex: "Instagram") — a comparação é
-- sempre normalizada (lower + trim dos dois lados), e só bate se o valor
-- normalizado for exatamente igual ao de algum dos 8 vendedores ativos.
-- utm_source vazio ('' ou só espaço) conta como ausente, igual a nulo.
--
-- O valor bruto do guest (utm_source_bruto) nunca é normalizado na fonte —
-- luma_guest.utm_source guarda exatamente o que a Luma devolveu. A view só
-- expõe, ao lado dele, a versão normalizada usada na comparação
-- (utm_source_normalizado), pra quem for revisar a fila de sem atribuição
-- conseguir ver o valor original (ex: "Instagram") sem precisar ir no
-- jsonb bruto.
--
-- Sem união com uma segunda origem: sem venda manual, todo ticket vem da
-- Luma, não existe mais coluna "origem".

create or replace view v_ingresso_atribuido as
with base as (
    select
        t.id as ticket_id,
        t.criado_em,
        t.valido,
        t.cupom_codigo,
        g.utm_source as utm_source_bruto,
        nullif(lower(trim(g.utm_source)), '') as utm_source_normalizado,
        ov.vendedor_id as vendedor_id_override,
        vu.id as vendedor_id_utm,
        vcv.id as vendedor_id_cupom
    from luma_ticket t
    join luma_guest g on g.id = t.guest_id
    left join atribuicao_override ov
        on ov.ticket_id = t.id
    left join vendedor vu
        on vu.ativo
        and nullif(lower(trim(g.utm_source)), '') is not null
        and lower(trim(vu.utm_source)) = lower(trim(g.utm_source))
    left join cupom_vendedor cv
        on cv.cupom_codigo = t.cupom_codigo
    left join vendedor vcv
        on vcv.id = cv.vendedor_id
        and vcv.ativo
)
select
    b.ticket_id,
    coalesce(b.vendedor_id_override, b.vendedor_id_utm, b.vendedor_id_cupom) as vendedor_id,
    v.time,
    b.valido,
    b.cupom_codigo,
    b.utm_source_bruto,
    b.utm_source_normalizado,
    b.criado_em,
    case
        when b.vendedor_id_override is not null then 'override'
        when b.vendedor_id_utm is not null then 'utm_source'
        when b.vendedor_id_cupom is not null then 'cupom'
        else 'sem_atribuicao'
    end as atribuido_por
from base b
left join vendedor v
    on v.id = coalesce(b.vendedor_id_override, b.vendedor_id_utm, b.vendedor_id_cupom);
