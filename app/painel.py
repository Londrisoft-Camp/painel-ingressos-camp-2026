"""
Gate 6 - Monta o payload de GET /api/painel (seção 7 do documento).

Só contagem de ingressos, nenhum valor monetário. Só entra na contagem
ingresso com atribuição resolvida e não reembolsado (`conta_no_painel` na
view `v_ingresso_atribuido`). Cortesia com atribuição conta igual a venda
paga — decisão da Mariana, não existe distinção aqui.

`semanaAtual` é sempre calculada a partir de `config.fase1_inicio` contra a
data de hoje (fuso America/Sao_Paulo), nunca fixada em código.

`semAtribuicao` é um número só, não por time: um ingresso sem atribuição
não tem vendedor, e por isso não tem time — não tem como saber se seria do
CSM ou do Comercial. Fica no topo do payload, não dentro de "csm"/"comercial".

`diasUteisRestantes` (topo do payload, mesmo raciocínio — a janela da
Fase 1 é uma só, não por time), `ritmoNecessario`, `diferencaSemana` e
`statusSemana` (por time) são calculados aqui, não no front: dias úteis
exclui fim de semana e os dois feriados que já entraram no cálculo de
`meta_semanal` (07/09 e 12/10/2026).

`gerentes` (quebra individual) agora existe nos dois times — decisão que
reverteu de novo a versão anterior, que tinha tirado do Comercial. Metas
não são iguais dentro do time (Comercial: Raul 10, os outros 30 cada), por
isso cada linha carrega a própria meta.

`topVendedores` é um ranking único juntando os dois times (não por time,
como `semAtribuicao`/`diasUteisRestantes`) — ordenado por realizado, com
empate desempatado por % da própria meta.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg

FUSO = ZoneInfo("America/Sao_Paulo")
TIMES = ("csm", "comercial")

# Feriados dentro da janela da Fase 1 (31/08 a 15/10/2026) — os mesmos dois
# que já reduziram os dias úteis de S2 e S7 em meta_semanal (migration 004).
FERIADOS = {date(2026, 9, 7), date(2026, 10, 12)}


def _hoje() -> date:
    return datetime.now(FUSO).date()


def _config(cur: psycopg.Cursor) -> dict[str, str]:
    cur.execute("select chave, valor from config")
    return dict(cur.fetchall())


def _calcular_semana_atual(fase1_inicio: date, hoje: date) -> int:
    dias = (hoje - fase1_inicio).days
    semana = dias // 7 + 1
    return max(1, min(semana, 7))


def _fim_da_semana(fase1_inicio: date, semana: int) -> date:
    return fase1_inicio + timedelta(days=semana * 7 - 1)


def _meta_acumulada(cur: psycopg.Cursor, time: str) -> list[int]:
    cur.execute("select meta_acumulada from meta_semanal where time = %s order by semana", (time,))
    return [r[0] for r in cur.fetchall()]


def _meta_total(cur: psycopg.Cursor, time: str) -> int:
    cur.execute("select coalesce(sum(meta), 0) from vendedor where time = %s and ativo", (time,))
    return cur.fetchone()[0]


def _realizado(cur: psycopg.Cursor, time: str) -> int:
    cur.execute(
        "select count(*) from v_ingresso_atribuido where time = %s and conta_no_painel",
        (time,),
    )
    return cur.fetchone()[0]


def _realizado_acumulado(
    cur: psycopg.Cursor, time: str, fase1_inicio: date, hoje: date, semana_atual: int
) -> list[int | None]:
    resultado: list[int | None] = []
    for semana in range(1, 8):
        if semana > semana_atual:
            resultado.append(None)
            continue
        cutoff = min(_fim_da_semana(fase1_inicio, semana), hoje)
        cur.execute(
            """
            select count(*) from v_ingresso_atribuido
            where time = %s and conta_no_painel
              and (criado_em at time zone 'America/Sao_Paulo')::date <= %s
            """,
            (time, cutoff),
        )
        resultado.append(cur.fetchone()[0])
    return resultado


def _vendedores(cur: psycopg.Cursor, time: str) -> list[dict]:
    """Quebra individual de um time. Metas não são iguais dentro do time
    (Comercial: Raul 10, os outros 30) — por isso cada linha carrega a
    própria meta, nunca um rótulo fixo tipo "meta X cada"."""
    cur.execute(
        """
        select v.nome, v.meta, coalesce(r.realizado, 0)
        from vendedor v
        left join (
            select vendedor_id, count(*) as realizado
            from v_ingresso_atribuido
            where time = %s and conta_no_painel
            group by vendedor_id
        ) r on r.vendedor_id = v.id
        where v.time = %s and v.ativo
        order by v.id
        """,
        (time, time),
    )
    return [{"nome": nome, "meta": meta, "realizado": realizado} for nome, meta, realizado in cur.fetchall()]


def _top_vendedores(cur: psycopg.Cursor, limite: int = 3) -> list[dict]:
    """Ranking único juntando os dois times. Empate em realizado desempata
    por % da própria meta -- as metas são diferentes entre e dentro dos
    times (10 a 75), comparar só o bruto não seria justo num empate."""
    cur.execute(
        """
        select v.nome, v.time, v.meta, coalesce(r.realizado, 0) as realizado
        from vendedor v
        left join (
            select vendedor_id, count(*) as realizado
            from v_ingresso_atribuido
            where conta_no_painel
            group by vendedor_id
        ) r on r.vendedor_id = v.id
        where v.ativo
        """
    )
    linhas = cur.fetchall()
    ranking = sorted(
        linhas,
        key=lambda linha: (-linha[3], -(linha[3] / linha[2] if linha[2] else 0)),
    )
    return [
        {"nome": nome, "time": time, "realizado": realizado}
        for nome, time, meta, realizado in ranking[:limite]
    ]


def _sem_atribuicao(cur: psycopg.Cursor) -> int:
    cur.execute("select count(*) from v_ingresso_atribuido where valido and vendedor_id is null")
    return cur.fetchone()[0]


def _dias_uteis_restantes(hoje: date, fase1_fim: date) -> int:
    if hoje > fase1_fim:
        return 0
    dias = 0
    d = hoje
    while d <= fase1_fim:
        if d.weekday() < 5 and d not in FERIADOS:
            dias += 1
        d += timedelta(days=1)
    return dias


def _ritmo_necessario(meta_total: int, realizado: int, dias_uteis_restantes: int) -> int:
    faltam = max(meta_total - realizado, 0)
    if dias_uteis_restantes <= 0:
        return faltam
    return math.ceil(faltam / dias_uteis_restantes)


def _status_semana(realizado_semana: int, meta_semana: int | None) -> str:
    """Três níveis, não dois: no_ritmo (bateu ou passou a meta da semana),
    atencao (até 20% abaixo), atrasado (mais de 20% abaixo)."""
    if not meta_semana:
        return "no_ritmo"
    if realizado_semana >= meta_semana:
        return "no_ritmo"
    if realizado_semana >= meta_semana * 0.8:
        return "atencao"
    return "atrasado"


def _atualizado_em(cur: psycopg.Cursor) -> str | None:
    cur.execute("select max(terminado_em) from sync_run where terminado_em is not null")
    momento = cur.fetchone()[0]
    if momento is None:
        return None
    return momento.astimezone(FUSO).strftime("%d/%m/%Y %H:%M")


def montar_payload(conn: psycopg.Connection) -> dict:
    with conn.cursor() as cur:
        config = _config(cur)
        fase1_inicio_str = config.get("fase1_inicio")
        fase1_fim_str = config.get("fase1_fim")
        hoje = _hoje()

        if fase1_inicio_str:
            fase1_inicio = date.fromisoformat(fase1_inicio_str)
            semana_atual = _calcular_semana_atual(fase1_inicio, hoje)
        else:
            fase1_inicio = None
            semana_atual = 1

        if fase1_fim_str:
            dias_uteis_restantes = _dias_uteis_restantes(hoje, date.fromisoformat(fase1_fim_str))
        else:
            dias_uteis_restantes = 0

        payload: dict = {
            "fonte": config.get("fonte_label", "Luma"),
            "atualizadoEm": _atualizado_em(cur),
            "semAtribuicao": _sem_atribuicao(cur),
            "diasUteisRestantes": dias_uteis_restantes,
            "topVendedores": _top_vendedores(cur),
        }

        for time in TIMES:
            meta_acumulada = _meta_acumulada(cur, time)
            realizado = _realizado(cur, time)
            meta_total = _meta_total(cur, time)
            if fase1_inicio is not None:
                realizado_acumulado = _realizado_acumulado(cur, time, fase1_inicio, hoje, semana_atual)
            else:
                realizado_acumulado = [None] * 7
            meta_semana = meta_acumulada[semana_atual - 1] if meta_acumulada else None

            bloco: dict = {
                "meta": meta_total,
                "realizado": realizado,
                "semanaAtual": semana_atual,
                "metaSemana": meta_semana,
                "realizadoSemana": realizado,
                "metaAcumulada": meta_acumulada,
                "realizadoAcumulado": realizado_acumulado,
                "ritmoNecessario": _ritmo_necessario(meta_total, realizado, dias_uteis_restantes),
                "diferencaSemana": realizado - meta_semana if meta_semana is not None else None,
                "statusSemana": _status_semana(realizado, meta_semana),
                "gerentes": _vendedores(cur, time),
            }
            payload[time] = bloco

    return payload
