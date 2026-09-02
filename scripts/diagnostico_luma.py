"""
Gate 1 - Diagnóstico da API Luma (read-only).

Script isolado: só lê da API da Luma e grava JSON cru em scripts/amostras/.
Não cria tabela, não modela schema, não grava em banco nenhum.

Uso:
    python scripts/diagnostico_luma.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

BASE_URL = "https://public-api.luma.com"
AMOSTRAS_DIR = Path(__file__).parent / "amostras"


def carregar_env() -> str:
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

    api_key = os.environ.get("LUMA_API_KEY", "").strip()
    if not api_key:
        print("ERRO: LUMA_API_KEY não definida (nem em .env nem no ambiente).", file=sys.stderr)
        sys.exit(1)
    return api_key


def salvar_amostra(nome: str, dado: dict) -> Path:
    AMOSTRAS_DIR.mkdir(parents=True, exist_ok=True)
    caminho = AMOSTRAS_DIR / nome
    caminho.write_text(json.dumps(dado, indent=2, ensure_ascii=False), encoding="utf-8")
    return caminho


def chamar(client: httpx.Client, path: str, params: dict | None = None) -> tuple[int, dict, dict]:
    resp = client.get(path, params=params or {})
    headers_relevantes = {
        k: v
        for k, v in resp.headers.items()
        if k.lower().startswith("x-ratelimit") or k.lower() == "retry-after"
    }
    print(f"GET {path} params={params} -> HTTP {resp.status_code}")
    if headers_relevantes:
        print(f"  rate-limit headers: {headers_relevantes}")
    try:
        corpo = resp.json()
    except json.JSONDecodeError:
        corpo = {"_raw_text_nao_json": resp.text}
    if resp.status_code >= 400:
        print(f"  ERRO: {json.dumps(corpo, ensure_ascii=False)[:2000]}")
    return resp.status_code, corpo, headers_relevantes


def main() -> None:
    api_key = carregar_env()
    client = httpx.Client(
        base_url=BASE_URL,
        headers={"x-luma-api-key": api_key},
        timeout=30.0,
    )

    resultado_doc: list[str] = []

    # 1. Listar eventos do calendário associado à API key
    status, corpo, headers = chamar(client, "/v1/calendars/events/list")
    salvar_amostra("events_list.json", {"status": status, "headers": headers, "body": corpo})
    resultado_doc.append(f"## GET /v1/calendars/events/list -> HTTP {status}")
    if status != 200:
        resultado_doc.append("Endpoint falhou. Ver corpo cru em `amostras/events_list.json`.")
        resultado_doc.append(f"```json\n{json.dumps(corpo, indent=2, ensure_ascii=False)[:3000]}\n```")
        Path(__file__).parent.joinpath("DIAGNOSTICO_LUMA.md").write_text(
            "\n\n".join(resultado_doc), encoding="utf-8"
        )
        print("\nParando: não é possível continuar sem listar eventos.")
        sys.exit(1)

    eventos = corpo.get("entries", [])
    resultado_doc.append(f"Retornou {len(eventos)} evento(s) nesta página. has_more={corpo.get('has_more')}")

    if not eventos:
        resultado_doc.append("Nenhum evento encontrado no calendário desta API key.")
        Path(__file__).parent.joinpath("DIAGNOSTICO_LUMA.md").write_text(
            "\n\n".join(resultado_doc), encoding="utf-8"
        )
        print("\nParando: calendário sem eventos, não há como testar guests/list e guests/get.")
        sys.exit(1)

    # Prioriza o evento "Londrisoft Camp 2026" (o evento real do projeto);
    # cai no primeiro da lista se não achar.
    def _normaliza(e):
        return e.get("event") if "event" in e else e

    evento = next(
        (_normaliza(e) for e in eventos if _normaliza(e).get("name", "").strip().lower() == "londrisoft camp 2026"),
        _normaliza(eventos[0]),
    )
    event_id = evento.get("api_id") or evento.get("id")
    resultado_doc.append(f"Usando o evento: `{event_id}` ({evento.get('name')})")

    # 2. Listar guests de um evento real
    status, corpo, headers = chamar(client, "/v1/events/guests/list", {"event_id": event_id})
    salvar_amostra("guests_list.json", {"status": status, "headers": headers, "body": corpo})
    resultado_doc.append(f"\n## GET /v1/events/guests/list -> HTTP {status}")
    if status != 200:
        resultado_doc.append("Endpoint falhou. Ver corpo cru em `amostras/guests_list.json`.")
        resultado_doc.append(f"```json\n{json.dumps(corpo, indent=2, ensure_ascii=False)[:3000]}\n```")
        Path(__file__).parent.joinpath("DIAGNOSTICO_LUMA.md").write_text(
            "\n\n".join(resultado_doc), encoding="utf-8"
        )
        print("\nParando: guests/list falhou.")
        sys.exit(1)

    guests = corpo.get("entries", [])
    resultado_doc.append(f"Retornou {len(guests)} guest(s) nesta página. has_more={corpo.get('has_more')}")

    if not guests:
        resultado_doc.append("Evento sem guests. Não há como testar guests/get com dado real.")
        Path(__file__).parent.joinpath("DIAGNOSTICO_LUMA.md").write_text(
            "\n\n".join(resultado_doc), encoding="utf-8"
        )
        print("\nAviso: evento sem guests, guests/get não foi testado.")
        sys.exit(0)

    guest = guests[0]
    guest_id = guest.get("api_id") or guest.get("id")
    resultado_doc.append(f"Usando o primeiro guest retornado: `{guest_id}`")

    # 3. Detalhe completo de um guest, com event_ticket_orders
    status, corpo, headers = chamar(
        client, "/v1/events/guests/get", {"event_id": event_id, "id": guest_id}
    )
    salvar_amostra("guest_get.json", {"status": status, "headers": headers, "body": corpo})
    resultado_doc.append(f"\n## GET /v1/events/guests/get -> HTTP {status}")
    if status != 200:
        resultado_doc.append("Endpoint falhou. Ver corpo cru em `amostras/guest_get.json`.")
        resultado_doc.append(f"```json\n{json.dumps(corpo, indent=2, ensure_ascii=False)[:3000]}\n```")

    Path(__file__).parent.joinpath("DIAGNOSTICO_LUMA.md").write_text(
        "\n\n".join(resultado_doc), encoding="utf-8"
    )
    print(f"\nAmostras salvas em {AMOSTRAS_DIR}")
    print("Resumo bruto salvo em scripts/DIAGNOSTICO_LUMA.md (será reescrito com análise completa).")


if __name__ == "__main__":
    main()
