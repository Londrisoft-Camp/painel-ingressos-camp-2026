"""Testes da regra de validade do Gate 4 — sync/run.py:calcular_valido.

Regra atual (decisão da Mariana, substitui a do Gate 1): valido cobre só
reembolso e cancelamento. is_captured não entra mais aqui — quem decide se
um ingresso aparece no painel é a atribuição, resolvida na view, não este
booleano sozinho.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from sync.run import calcular_valido, marcar_tickets_sumidos_do_guest

EVENT_ID = "evt-59xGdD8EixaTOAa"


@pytest.mark.parametrize(
    "order, guest, esperado, motivo",
    [
        (
            {"amount_refunded": 0},
            {"approval_status": "approved"},
            True,
            "sem reembolso, aprovado -> válido",
        ),
        (
            {"amount_refunded": 0},
            {"approval_status": "approved"},
            True,
            "ingresso grátis intencional (amount 0) também é válido -- is_captured não entra mais na conta",
        ),
        (
            {"amount_refunded": 19850},
            {"approval_status": "approved"},
            False,
            "reembolsado -> não conta, independente de atribuição",
        ),
        (
            {"amount_refunded": 0},
            {"approval_status": "declined"},
            False,
            "guest declinado -> não conta mesmo sem reembolso registrado",
        ),
        (
            {"amount_refunded": 0},
            {"approval_status": "waitlist"},
            False,
            "guest na lista de espera -> não conta",
        ),
        (
            {},  # order sem event_ticket_orders (ex: falha ao casar ticket com order)
            {"approval_status": "approved"},
            True,
            "amount_refunded ausente é tratado como 0, não quebra",
        ),
        (
            {"amount_refunded": 19850},
            {"approval_status": "declined"},
            False,
            "dois motivos ao mesmo tempo -> ainda inválido",
        ),
    ],
)
def test_calcular_valido(order, guest, esperado, motivo):
    assert calcular_valido(order, guest) is esperado, motivo


def _carregar_database_url() -> str:
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for linha in env_path.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            valor = valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            os.environ.setdefault(chave.strip(), valor)
    return os.environ["DATABASE_URL"]


@pytest.fixture
def conn():
    connection = psycopg.connect(_carregar_database_url())
    yield connection
    connection.rollback()  # nunca commita — nada do teste sobrevive
    connection.close()


def test_ticket_some_do_guest_declinado_vira_invalido(conn):
    """Achado em produção (16/09): guest recusado depois de já ter
    ingresso esvazia o event_tickets dele no guests/list, sem nunca
    aparecer como reembolsado. O ticket antigo tem que virar inválido
    assim que isso é detectado -- não só no --full do dia seguinte."""
    guest_id = "teste-gst-sumido"
    ticket_id = "teste-tkt-sumido"
    with conn.cursor() as cur:
        cur.execute(
            "insert into luma_guest (id, event_id, nome, email, status, raw) values (%s, %s, 'Teste', 't@example.com', 'approved', %s)",
            (guest_id, EVENT_ID, Jsonb({})),
        )
        cur.execute(
            "insert into luma_ticket (id, guest_id, event_id, valido, raw) values (%s, %s, %s, true, %s)",
            (ticket_id, guest_id, EVENT_ID, Jsonb({})),
        )
        # guest foi recusado -- event_tickets agora vem vazio, ids_atuais = {}
        marcar_tickets_sumidos_do_guest(cur, guest_id, set())
        cur.execute("select valido from luma_ticket where id = %s", (ticket_id,))
        assert cur.fetchone()[0] is False


def test_ticket_que_continua_na_lista_nao_e_tocado(conn):
    """Guest com 2 tickets que perde só 1 -- o que sumiu vira inválido, o
    que continua aparecendo na lista não é mexido."""
    guest_id = "teste-gst-parcial"
    ticket_fica = "teste-tkt-fica"
    ticket_some = "teste-tkt-some"
    with conn.cursor() as cur:
        cur.execute(
            "insert into luma_guest (id, event_id, nome, email, status, raw) values (%s, %s, 'Teste', 't@example.com', 'approved', %s)",
            (guest_id, EVENT_ID, Jsonb({})),
        )
        for tid in (ticket_fica, ticket_some):
            cur.execute(
                "insert into luma_ticket (id, guest_id, event_id, valido, raw) values (%s, %s, %s, true, %s)",
                (tid, guest_id, EVENT_ID, Jsonb({})),
            )
        marcar_tickets_sumidos_do_guest(cur, guest_id, {ticket_fica})
        cur.execute("select id, valido from luma_ticket where id in (%s, %s)", (ticket_fica, ticket_some))
        resultado = dict(cur.fetchall())
        assert resultado[ticket_fica] is True
        assert resultado[ticket_some] is False
