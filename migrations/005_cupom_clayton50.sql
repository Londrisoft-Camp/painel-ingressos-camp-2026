-- Cupom real confirmado em uso no evento (2 ingressos válidos: Oswaldo
-- Aranda Filho, Full Pass - 1° Lote). Mapeado pra Clayton por instrução
-- explícita, depois de puxar a lista completa de cupons direto da Luma —
-- não semeado de memória.

insert into cupom_vendedor (cupom_codigo, vendedor_id, observacao)
select
    'CLAYTON50',
    id,
    'Cupom real confirmado em uso no evento (Gate 4). Mapeado pra Clayton por instrução explícita.'
from vendedor
where utm_source = 'clayton'
on conflict (cupom_codigo) do nothing;
