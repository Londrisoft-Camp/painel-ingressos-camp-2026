-- Nova regra de contagem, decidida pela Mariana, substitui a do Gate 1:
--   - is_captured deixa de ser critério de exclusão. Ingresso grátis
--     intencional conta igual a pago.
--   - Quem decide se um ingresso aparece no painel é a ATRIBUIÇÃO
--     (utm_source batendo com vendedor ativo, ou cupom mapeado pra
--     vendedor ativo em cupom_vendedor) — não o valido sozinho.
--   - Sem atribuição, o ingresso continua gravado e visível na fila de
--     revisão, só não entra em soma nenhuma (nem time, nem Geral, nem
--     individual).
--   - Reembolso continua excluindo sempre, independente de atribuição.
--   - Nenhum valor monetário gravado ou calculado.
--
-- valido passa a cobrir só reembolso e cancelamento (não mais captura).

-- Recalcula valido dos tickets já sincronizados a partir do raw jsonb já
-- gravado — não precisa rodar o sync de novo pra aplicar a regra nova.
update luma_ticket t
set valido = not (
    coalesce((t.raw -> 'order' ->> 'amount_refunded')::integer, 0) > 0
    or g.status in ('declined', 'waitlist')
)
from luma_guest g
where g.id = t.guest_id;

-- View: só entra em contagem (conta_no_painel) se valido E tiver
-- atribuição resolvida. Sem atribuição continua aparecendo na view (pra
-- fila de revisão), só com conta_no_painel = false.
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
),
resolvido as (
    select
        b.*,
        coalesce(b.vendedor_id_override, b.vendedor_id_utm, b.vendedor_id_cupom) as vendedor_id
    from base b
)
select
    r.ticket_id,
    r.vendedor_id,
    v.time,
    r.valido,
    r.cupom_codigo,
    r.utm_source_bruto,
    r.utm_source_normalizado,
    r.criado_em,
    case
        when r.vendedor_id_override is not null then 'override'
        when r.vendedor_id_utm is not null then 'utm_source'
        when r.vendedor_id_cupom is not null then 'cupom'
        else 'sem_atribuicao'
    end as atribuido_por,
    (r.valido and r.vendedor_id is not null) as conta_no_painel
from resolvido r
left join vendedor v on v.id = r.vendedor_id;
