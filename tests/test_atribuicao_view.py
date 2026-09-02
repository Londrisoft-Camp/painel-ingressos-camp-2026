"""Gate 5 — prova a view v_ingresso_atribuido contra o Neon real.

A resolução de atribuição inteira vive em SQL (003/006), não existe
sync/atribuicao.py separado. Este arquivo não mocka nada: conecta no Neon
de verdade e testa a view real. Cada teste insere guest/ticket sintéticos
dentro de uma transação que é sempre revertida no teardown (nunca commita)
— não polui o dado real do Camp. Reusa o event_id real só pra satisfazer a
FK, os ids de guest/ticket são todos prefixados "teste-" pra nunca colidir
com o que o sync já gravou.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

EVENT_ID = "evt-59xGdD8EixaTOAa"


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


def _vendedor_id(cur: psycopg.Cursor, utm_source: str) -> int:
    cur.execute("select id from vendedor where utm_source = %s", (utm_source,))
    return cur.fetchone()[0]


def _inserir(
    cur: psycopg.Cursor,
    *,
    ticket_id: str,
    guest_id: str,
    utm_source: str | None = None,
    cupom_codigo: str | None = None,
    valido: bool = True,
    approval_status: str = "approved",
) -> None:
    cur.execute(
        """
        insert into luma_guest (id, event_id, nome, email, status, utm_source, raw)
        values (%s, %s, 'Teste Gate5', 'teste-gate5@example.com', %s, %s, %s)
        """,
        (guest_id, EVENT_ID, approval_status, utm_source, Jsonb({})),
    )
    cur.execute(
        """
        insert into luma_ticket (id, guest_id, event_id, cupom_codigo, valido, raw)
        values (%s, %s, %s, %s, %s, %s)
        """,
        (ticket_id, guest_id, EVENT_ID, cupom_codigo, valido, Jsonb({})),
    )


def _resultado(cur: psycopg.Cursor, ticket_id: str):
    cur.execute(
        """
        select vendedor_id, time, valido, atribuido_por, conta_no_painel, utm_source_bruto
        from v_ingresso_atribuido where ticket_id = %s
        """,
        (ticket_id,),
    )
    return cur.fetchone()


def test_utm_source_batendo(conn):
    with conn.cursor() as cur:
        _inserir(cur, ticket_id="teste-tkt-1", guest_id="teste-gst-1", utm_source="gian")
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, "teste-tkt-1")
        assert atribuido_por == "utm_source"
        assert time == "csm"
        assert conta is True
        assert vendedor_id == _vendedor_id(cur, "gian")


def test_utm_source_capitalizado_bate_depois_de_normalizar(conn):
    with conn.cursor() as cur:
        _inserir(cur, ticket_id="teste-tkt-2", guest_id="teste-gst-2", utm_source="Lucineia")
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, "teste-tkt-2")
        assert atribuido_por == "utm_source"
        assert vendedor_id == _vendedor_id(cur, "lucineia")
        assert utm_bruto == "Lucineia"  # o bruto não normaliza, só a comparação


def test_utm_source_de_canal_nao_vendedor_cai_em_sem_atribuicao(conn):
    with conn.cursor() as cur:
        _inserir(cur, ticket_id="teste-tkt-3", guest_id="teste-gst-3", utm_source="Instagram")
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, "teste-tkt-3")
        assert atribuido_por == "sem_atribuicao"
        assert conta is False
        assert utm_bruto == "Instagram"  # visível pra revisão, não sumiu


def test_utm_source_vazio_conta_como_ausente(conn):
    with conn.cursor() as cur:
        _inserir(cur, ticket_id="teste-tkt-4", guest_id="teste-gst-4", utm_source="")
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, "teste-tkt-4")
        assert atribuido_por == "sem_atribuicao"
        assert conta is False


def test_cupom_rafa50_sem_vendedor_ativo_nao_estoura(conn):
    with conn.cursor() as cur:
        _inserir(cur, ticket_id="teste-tkt-5", guest_id="teste-gst-5", cupom_codigo="RAFA50")
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, "teste-tkt-5")
        assert atribuido_por == "sem_atribuicao"
        assert vendedor_id is None
        assert conta is False


@pytest.mark.parametrize("cupom, utm_esperado", [("LUVIP", "lucineia"), ("CLAYTON50", "clayton")])
def test_cupom_com_vendedor_ativo_resolve(conn, cupom, utm_esperado):
    with conn.cursor() as cur:
        ticket_id = f"teste-tkt-cupom-{cupom}"
        _inserir(cur, ticket_id=ticket_id, guest_id=f"teste-gst-cupom-{cupom}", cupom_codigo=cupom)
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, ticket_id)
        assert atribuido_por == "cupom"
        assert conta is True
        assert vendedor_id == _vendedor_id(cur, utm_esperado)


def test_cupom_que_nao_esta_na_tabela_cai_em_sem_atribuicao(conn):
    # Código fictício de propósito -- nunca usar um cupom real aqui, porque
    # cupons reais podem ganhar mapeamento numa migration futura (foi
    # exatamente o que aconteceu com PREMIUMIWA) e quebrar este teste.
    with conn.cursor() as cur:
        _inserir(cur, ticket_id="teste-tkt-6", guest_id="teste-gst-6", cupom_codigo="CUPOM-FICTICIO-TESTE")
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, "teste-tkt-6")
        assert atribuido_por == "sem_atribuicao"
        assert conta is False


def test_sem_cupom_e_sem_utm_source(conn):
    with conn.cursor() as cur:
        _inserir(cur, ticket_id="teste-tkt-7", guest_id="teste-gst-7")
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, "teste-tkt-7")
        assert atribuido_por == "sem_atribuicao"
        assert conta is False


def test_override_vence_utm_source_e_cupom(conn):
    with conn.cursor() as cur:
        _inserir(
            cur,
            ticket_id="teste-tkt-8",
            guest_id="teste-gst-8",
            utm_source="clayton",  # indicaria Clayton
            cupom_codigo="LUVIP",  # indicaria Lucineia
        )
        vendedor_override = _vendedor_id(cur, "gian")  # override manda pra um terceiro, Gian
        cur.execute(
            "insert into atribuicao_override (ticket_id, vendedor_id, motivo, autor) values (%s, %s, %s, %s)",
            ("teste-tkt-8", vendedor_override, "teste do Gate 5", "pytest"),
        )
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, "teste-tkt-8")
        assert atribuido_por == "override"
        assert vendedor_id == vendedor_override
        assert conta is True


def test_reembolsado_nao_conta_mesmo_com_atribuicao_resolvida(conn):
    with conn.cursor() as cur:
        _inserir(cur, ticket_id="teste-tkt-9", guest_id="teste-gst-9", utm_source="patricia", valido=False)
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, "teste-tkt-9")
        assert atribuido_por == "utm_source"  # a atribuição resolve normalmente...
        assert valido is False
        assert conta is False  # ...mas não conta, porque valido é false


def test_valido_e_sem_atribuicao_nao_conta_por_falta_de_atribuicao(conn):
    """Ingresso não reembolsado (valido=true), sem utm_source e sem cupom.
    conta_no_painel precisa ser false por falta de atribuição — não por
    causa de captura, que não existe mais nessa conta (decisão da Mariana)."""
    with conn.cursor() as cur:
        _inserir(cur, ticket_id="teste-tkt-10", guest_id="teste-gst-10", valido=True)
        vendedor_id, time, valido, atribuido_por, conta, utm_bruto = _resultado(cur, "teste-tkt-10")
        assert valido is True
        assert atribuido_por == "sem_atribuicao"
        assert conta is False
