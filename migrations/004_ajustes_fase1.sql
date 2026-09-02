-- Corrige os valores provisórios semeados em 002_negocio.sql agora que a
-- Fase 1 e o calendário de dias úteis foram fechados (31/08 a 15/10/2026,
-- 7 semanas, feriados em 07/09 e 12/10). A 002 já tinha rodado contra o
-- Neon, então a correção entra como migration nova — nunca se edita uma
-- migration já aplicada.

insert into meta_semanal (time, semana, meta_acumulada) values
    ('csm', 1, 28), ('csm', 2, 68), ('csm', 3, 116), ('csm', 4, 168),
    ('csm', 5, 220), ('csm', 6, 272), ('csm', 7, 300),
    ('comercial', 1, 9), ('comercial', 2, 22), ('comercial', 3, 38),
    ('comercial', 4, 55), ('comercial', 5, 72), ('comercial', 6, 89),
    ('comercial', 7, 100)
on conflict (time, semana) do update set meta_acumulada = excluded.meta_acumulada;

insert into config (chave, valor) values
    ('fase1_inicio', '2026-08-31'),
    ('fase1_fim', '2026-10-15'),
    ('data_evento', '2026-11-11')
on conflict (chave) do update set valor = excluded.valor;
