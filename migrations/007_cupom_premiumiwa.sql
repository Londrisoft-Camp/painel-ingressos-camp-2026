-- Cupom real confirmado em uso no evento (2 ingressos: Matheus Aguiar de
-- Araújo, Silas Barroso Schimith, Premium Pass - VIP). Mapeado pro
-- Guilherme por instrução explícita da Mariana.

insert into cupom_vendedor (cupom_codigo, vendedor_id, observacao)
select
    'PREMIUMIWA',
    id,
    'Cupom real confirmado em uso no evento (Gate 4/6). Mapeado pro Guilherme por instrução explícita da Mariana.'
from vendedor
where utm_source = 'guilherme'
on conflict (cupom_codigo) do nothing;
