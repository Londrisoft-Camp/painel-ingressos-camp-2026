-- Cupom real em uso no evento (3 ingressos em 14/10: João Vitor da Costa
-- Andrade, Anelise Franciosi, Magali Roco, Premium Pass - VIP). Sem link de
-- vendedor, caíam em sem_atribuicao. Mapeado pro Raul (Comercial) por
-- instrução explícita da Mariana, depois de puxar a lista de cupons direto
-- da Luma.

insert into cupom_vendedor (cupom_codigo, vendedor_id, observacao)
select
    'PREMIUMCOM',
    id,
    'Cupom real confirmado em uso no evento (14/10). Mapeado pro Raul por instrução explícita da Mariana.'
from vendedor
where utm_source = 'raul'
on conflict (cupom_codigo) do nothing;
