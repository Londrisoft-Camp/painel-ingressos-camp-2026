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
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg

FUSO = ZoneInfo("America/Sao_Paulo")
TIMES = ("csm", "comercial")


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


def _gerentes_csm(cur: psycopg.Cursor) -> list[dict]:
    cur.execute(
        """
        select v.nome, v.meta, coalesce(r.realizado, 0)
        from vendedor v
        left join (
            select vendedor_id, count(*) as realizado
            from v_ingresso_atribuido
            where time = 'csm' and conta_no_painel
            group by vendedor_id
        ) r on r.vendedor_id = v.id
        where v.time = 'csm' and v.ativo
        order by v.id
        """
    )
    return [{"nome": nome, "meta": meta, "realizado": realizado} for nome, meta, realizado in cur.fetchall()]


def _sem_atribuicao(cur: psycopg.Cursor) -> int:
    cur.execute("select count(*) from v_ingresso_atribuido where valido and vendedor_id is null")
    return cur.fetchone()[0]


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
        hoje = _hoje()

        if fase1_inicio_str:
            fase1_inicio = date.fromisoformat(fase1_inicio_str)
            semana_atual = _calcular_semana_atual(fase1_inicio, hoje)
        else:
            fase1_inicio = None
            semana_atual = 1

        payload: dict = {
            "fonte": config.get("fonte_label", "Luma"),
            "atualizadoEm": _atualizado_em(cur),
            "semAtribuicao": _sem_atribuicao(cur),
        }

        for time in TIMES:
            meta_acumulada = _meta_acumulada(cur, time)
            realizado = _realizado(cur, time)
            if fase1_inicio is not None:
                realizado_acumulado = _realizado_acumulado(cur, time, fase1_inicio, hoje, semana_atual)
            else:
                realizado_acumulado = [None] * 7
            meta_semana = meta_acumulada[semana_atual - 1] if meta_acumulada else None

            bloco: dict = {
                "meta": _meta_total(cur, time),
                "realizado": realizado,
                "semanaAtual": semana_atual,
                "metaSemana": meta_semana,
                "realizadoSemana": realizado,
                "metaAcumulada": meta_acumulada,
                "realizadoAcumulado": realizado_acumulado,
            }
            if time == "csm":
                bloco["gerentes"] = _gerentes_csm(cur)
            payload[time] = bloco

    return payload
