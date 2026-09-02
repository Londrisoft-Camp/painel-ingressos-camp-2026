"""Testes da regra de validade do Gate 4 — sync/run.py:calcular_valido.

Regra atual (decisão da Mariana, substitui a do Gate 1): valido cobre só
reembolso e cancelamento. is_captured não entra mais aqui — quem decide se
um ingresso aparece no painel é a atribuição, resolvida na view, não este
booleano sozinho.
"""

import pytest

from sync.run import calcular_valido


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
