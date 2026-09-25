-- Achado real em produção (18/09): a Lucineia divulgou link(s) com hora
-- grudada no utm_source ("lucineia15:56", "lucineia13:30"), e os guests
-- vieram também com cupom "CSM~PREMIUM"/"CSM%70" -- nenhum dos dois cadastrado
-- em cupom_vendedor. Resultado: 6 ingressos dela caindo em sem_atribuicao,
-- mesmo o utm_source claramente indicando de quem é a venda.
--
-- Decisão da Mariana: quando o cupom não identifica ninguém, o painel deve
-- olhar o utm_source pra ver se é de algum vendedor -- e se o valor do guest
-- começa com o utm_source de um vendedor ativo (não precisa mais ser igual
-- caractere por caractere), atribui a ele. utm_source de canal (ex:
-- "Instagram") continua não batendo com ninguém, porque nenhum vendedor
-- cadastrado tem esse prefixo. Sem nome (utm) e sem cupom mapeado, continua
-- sem entrar em soma nenhuma -- isso não muda.
--
-- Implementado como lateral com "order by length(...) desc limit 1" em vez
-- de um "like" direto no join, pra nunca duplicar a linha do ticket caso o
-- utm_source do guest um dia comece a bater o prefixo de mais de um
-- vendedor ativo ao mesmo tempo -- fica sempre o prefixo mais específico.

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
    left join lateral (
        select v.id
        from vendedor v
        where v.ativo
          and nullif(lower(trim(g.utm_source)), '') is not null
          and lower(trim(g.utm_source)) like lower(trim(v.utm_source)) || '%'
        order by length(v.utm_source) desc
        limit 1
    ) vu on true
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
