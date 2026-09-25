"""Consulta de status de cadastro, pra vendedor (gerente de conta ou
comercial) conferir sozinho se o cliente dele contou no painel — sem
precisar perguntar pra Mariana toda hora.

Não revela pra quem um ingresso está atribuído quando não é de quem está
consultando, nem o e-mail de um cadastro que não é dele — só diz que já
está com outra pessoa da equipe ou sem atribuição.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import psycopg

FUSO = ZoneInfo("America/Sao_Paulo")


def listar_vendedores(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("select id, nome, time from vendedor where ativo order by time, nome")
        return [{"id": i, "nome": nome, "time": time} for i, nome, time in cur.fetchall()]


def buscar(conn: psycopg.Connection, busca: str, vendedor_id: int) -> dict:
    termo = f"%{busca.strip()}%"
    with conn.cursor() as cur:
        cur.execute(
            """
            select g.nome, g.email, t.ticket_type_nome, va.valido, va.conta_no_painel, va.vendedor_id
            from luma_guest g
            join luma_ticket t on t.guest_id = g.id
            join v_ingresso_atribuido va on va.ticket_id = t.id
            where g.nome ilike %s or g.email ilike %s
            order by t.criado_em desc
            limit 10
            """,
            (termo, termo),
        )
        linhas = cur.fetchall()

    resultados = []
    for nome, email, tipo_ingresso, valido, conta_no_painel, vendedor_id_ticket in linhas:
        eh_seu = vendedor_id_ticket == vendedor_id
        if not valido:
            status = "cancelado"
        elif not conta_no_painel:
            status = "sem_atribuicao"
        elif eh_seu:
            status = "seu"
        else:
            status = "outro"
        resultados.append(
            {
                "nome": nome,
                "email": email if eh_seu else None,
                "tipoIngresso": tipo_ingresso,
                "status": status,
            }
        )

    return {"encontrado": bool(resultados), "resultados": resultados}


def ultimos(conn: psycopg.Connection, vendedor_id: int, limite: int = 5) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            select g.nome, g.email, t.ticket_type_nome, t.criado_em
            from luma_guest g
            join luma_ticket t on t.guest_id = g.id
            join v_ingresso_atribuido va on va.ticket_id = t.id
            where va.vendedor_id = %s and va.conta_no_painel
            order by t.criado_em desc
            limit %s
            """,
            (vendedor_id, limite),
        )
        linhas = cur.fetchall()

    resultados = [
        {
            "nome": nome,
            "email": email,
            "tipoIngresso": tipo_ingresso,
            "criadoEm": criado_em.astimezone(FUSO).strftime("%d/%m/%Y %H:%M") if criado_em else None,
            "status": "seu",
        }
        for nome, email, tipo_ingresso, criado_em in linhas
    ]

    return {"encontrado": bool(resultados), "resultados": resultados}
