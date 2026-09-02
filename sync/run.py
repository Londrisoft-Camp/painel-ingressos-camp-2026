"""
Gate 4 - Sync: lê a Luma via sync/luma.py e grava no Neon. Upsert por id,
nunca delete. Nunca toca em atribuicao_override.

Dois modos:
    --incremental (padrão, é o que o cron roda)
        só processa guest novo ou cujo raw mudou desde a última leitura
    --full
        reprocessa todo mundo (precisa, porque amount_refunded só aparece
        no guests/get, então só uma varredura completa pega reembolso) e
        marca como valido = false qualquer ticket do evento que não
        apareceu nesta varredura

Nenhum valor monetário é gravado ou calculado. amount/amount_discount/
amount_refunded só existem em memória, o tempo de decidir o booleano
`valido` — o que sobrevive em disco é esse booleano e o raw jsonb (a
resposta original da Luma, pra reprocessar sem bater na API de novo).

utm_source é gravado exatamente como a Luma manda. A normalização
(lower/trim) só acontece na view v_ingresso_atribuido, na leitura.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from sync.luma import LumaAPIError, LumaClient

NOME_EVENTO = "Londrisoft Camp 2026"

# approval_status do guest que indicam cancelamento/não comparecimento.
# Combinado com amount_refunded pra decidir "reembolsado ou cancelado" —
# não existe um campo único da Luma pra isso (achado do Gate 1).
STATUS_CANCELADO = ("declined", "waitlist")


def carregar_env() -> None:
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


def calcular_valido(order: dict[str, Any], guest: dict[str, Any]) -> bool:
    """`valido` cobre só reembolso e cancelamento — não é captura.

    Decisão da Mariana que substitui a regra do Gate 1: is_captured deixa
    de ser critério de exclusão, ingresso grátis intencional conta igual a
    pago. Quem decide se um ingresso aparece no painel é a atribuição
    (resolvida na view v_ingresso_atribuido), não este booleano sozinho.
    Reembolso continua excluindo sempre, independente de atribuição.
    amount_refunded nunca é gravado — só usado aqui, na hora, pra decidir
    esse booleano."""
    amount_refunded = order.get("amount_refunded") or 0
    status = guest.get("approval_status")
    reembolsado_ou_cancelado = amount_refunded > 0 or status in STATUS_CANCELADO
    return not reembolsado_ou_cancelado


def upsert_evento(cur: psycopg.Cursor, evento: dict[str, Any]) -> str:
    event_id = evento.get("api_id") or evento["id"]
    cur.execute(
        """
        insert into luma_event (id, nome, calendario_id, inicio_em, raw, sincronizado_em)
        values (%s, %s, %s, %s, %s, now())
        on conflict (id) do update set
            nome = excluded.nome,
            calendario_id = excluded.calendario_id,
            inicio_em = excluded.inicio_em,
            raw = excluded.raw,
            sincronizado_em = now()
        """,
        (event_id, evento.get("name"), evento.get("calendar_id"), evento.get("start_at"), Jsonb(evento)),
    )
    return event_id


def guest_mudou(cur: psycopg.Cursor, guest: dict[str, Any]) -> bool:
    cur.execute("select raw from luma_guest where id = %s", (guest["id"],))
    linha = cur.fetchone()
    return linha is None or linha[0] != guest


def upsert_guest(cur: psycopg.Cursor, guest: dict[str, Any], event_id: str) -> None:
    cur.execute(
        """
        insert into luma_guest
            (id, event_id, nome, email, status, utm_source, registrado_em, raw, sincronizado_em)
        values (%s, %s, %s, %s, %s, %s, %s, %s, now())
        on conflict (id) do update set
            event_id = excluded.event_id,
            nome = excluded.nome,
            email = excluded.email,
            status = excluded.status,
            utm_source = excluded.utm_source,
            registrado_em = excluded.registrado_em,
            raw = excluded.raw,
            sincronizado_em = now()
        """,
        (
            guest["id"],
            event_id,
            guest.get("user_name"),
            guest.get("user_email"),
            guest.get("approval_status"),
            guest.get("utm_source"),  # cru, sem normalizar
            guest.get("registered_at"),
            Jsonb(guest),
        ),
    )


def upsert_ticket(cur: psycopg.Cursor, ticket: dict[str, Any], order: dict[str, Any], guest: dict[str, Any], event_id: str) -> None:
    valido = calcular_valido(order, guest)
    cupom_codigo = (order.get("coupon_info") or {}).get("code")
    cur.execute(
        """
        insert into luma_ticket
            (id, guest_id, event_id, ticket_type_id, ticket_type_nome, cupom_codigo,
             valido, checked_in, criado_em, raw, sincronizado_em)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        on conflict (id) do update set
            guest_id = excluded.guest_id,
            event_id = excluded.event_id,
            ticket_type_id = excluded.ticket_type_id,
            ticket_type_nome = excluded.ticket_type_nome,
            cupom_codigo = excluded.cupom_codigo,
            valido = excluded.valido,
            checked_in = excluded.checked_in,
            criado_em = excluded.criado_em,
            raw = excluded.raw,
            sincronizado_em = now()
        """,
        (
            ticket["id"],
            guest["id"],
            event_id,
            ticket.get("event_ticket_type_id"),
            ticket.get("name"),
            cupom_codigo,
            valido,
            ticket.get("checked_in_at") is not None,
            guest.get("registered_at"),  # a Luma não expõe criado_em do ticket em si
            Jsonb({"ticket": ticket, "order": order}),
        ),
    )


def marcar_sumidos_como_invalidos(cur: psycopg.Cursor, event_id: str, ids_vistos: set[str]) -> int:
    if ids_vistos:
        cur.execute(
            """
            update luma_ticket set valido = false, sincronizado_em = now()
            where event_id = %s and valido = true and not (id = any(%s))
            """,
            (event_id, list(ids_vistos)),
        )
    else:
        cur.execute(
            "update luma_ticket set valido = false, sincronizado_em = now() where event_id = %s and valido = true",
            (event_id,),
        )
    return cur.rowcount


def rodar(modo: str) -> dict[str, Any]:
    carregar_env()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    api_key = os.environ.get("LUMA_API_KEY", "").strip()
    if not database_url or not api_key:
        print("ERRO: DATABASE_URL e LUMA_API_KEY precisam estar definidas.", file=sys.stderr)
        sys.exit(1)

    guests_lidos = 0
    tickets_lidos = 0
    erros = 0
    ids_vistos: set[str] = set()

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into sync_run (tipo) values (%s) returning id", (modo,))
            sync_run_id = cur.fetchone()[0]
        conn.commit()

        try:
            with LumaClient(api_key=api_key) as client:
                eventos = list(client.listar_eventos())
                evento = next((e for e in eventos if e.get("name") == NOME_EVENTO), None)
                if evento is None:
                    raise RuntimeError(f'Evento "{NOME_EVENTO}" não encontrado no calendário.')

                with conn.cursor() as cur:
                    event_id = upsert_evento(cur, evento)
                conn.commit()

                for guest in client.listar_guests(event_id=event_id):
                    guests_lidos += 1

                    with conn.cursor() as cur:
                        mudou = guest_mudou(cur, guest)

                    # --full sempre reprocessa: amount_refunded só aparece no
                    # guests/get, então só uma varredura completa pega reembolso.
                    if modo != "full" and not mudou:
                        continue

                    with conn.cursor() as cur:
                        upsert_guest(cur, guest, event_id)
                    conn.commit()

                    tickets_do_guest = guest.get("event_tickets") or []
                    if not tickets_do_guest:
                        continue

                    try:
                        detalhe = client.obter_guest(event_id=event_id, guest_id=guest["id"])
                    except LumaAPIError as e:
                        erros += 1
                        print(f"erro ao buscar detalhe de {guest['id']}: {e}", file=sys.stderr)
                        continue

                    orders = detalhe.get("event_ticket_orders") or []
                    for i, ticket in enumerate(tickets_do_guest):
                        order = orders[i] if i < len(orders) else {}
                        with conn.cursor() as cur:
                            upsert_ticket(cur, ticket, order, guest, event_id)
                        conn.commit()
                        tickets_lidos += 1
                        if modo == "full":
                            ids_vistos.add(ticket["id"])

                invalidados = 0
                if modo == "full":
                    with conn.cursor() as cur:
                        invalidados = marcar_sumidos_como_invalidos(cur, event_id, ids_vistos)
                    conn.commit()

            with conn.cursor() as cur:
                cur.execute(
                    """
                    update sync_run set terminado_em = now(), guests_lidos = %s,
                        tickets_lidos = %s, erros = %s, detalhe = %s
                    where id = %s
                    """,
                    (
                        guests_lidos,
                        tickets_lidos,
                        erros,
                        Jsonb({"invalidados_por_reconciliacao": invalidados} if modo == "full" else {}),
                        sync_run_id,
                    ),
                )
            conn.commit()

        except Exception as e:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update sync_run set terminado_em = now(), guests_lidos = %s,
                        tickets_lidos = %s, erros = %s, detalhe = %s
                    where id = %s
                    """,
                    (guests_lidos, tickets_lidos, erros + 1, Jsonb({"erro_fatal": str(e)}), sync_run_id),
                )
            conn.commit()
            raise

    return {"guests_lidos": guests_lidos, "tickets_lidos": tickets_lidos, "erros": erros}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Luma -> Neon")
    parser.add_argument("--full", action="store_true", help="varredura completa com reconciliação")
    args = parser.parse_args()
    modo = "full" if args.full else "incremental"

    resultado = rodar(modo)
    print(f"sync {modo} concluído: {resultado}")


if __name__ == "__main__":
    main()
