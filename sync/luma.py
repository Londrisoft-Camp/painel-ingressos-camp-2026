"""
Gate 3 - Client HTTP para a API pública da Luma.

Só devolve objetos Python (dicts) — não grava nada em banco, não conhece o
Postgres. Endpoints, formato de paginação e comportamento de erro conforme
o que o Gate 1 confirmou contra a API real (ver scripts/DIAGNOSTICO_LUMA.md).
"""

from __future__ import annotations

import time
from typing import Any, Iterator

import httpx

BASE_URL = "https://public-api.luma.com"

# Teto real da Luma é 200 requisições/minuto por calendário. Paceamos
# abaixo disso de propósito, pra deixar folga e nunca chegar perto do 429.
RITMO_REQ_POR_MIN = 150
INTERVALO_MIN_ENTRE_REQS = 60.0 / RITMO_REQ_POR_MIN  # segundos

MAX_TENTATIVAS = 5
BACKOFF_TETO_SEGUNDOS = 60.0


class LumaAPIError(Exception):
    """Erro vindo da API da Luma, com status e corpo cru preservados.

    Não contorna nada: quem chama decide o que fazer com um 403 (evento sem
    acesso, não necessariamente inexistente), um 400 (parâmetro faltando)
    ou um 401 (chave inválida) — achados reais do Gate 1.
    """

    def __init__(self, status_code: int, corpo: Any, path: str) -> None:
        self.status_code = status_code
        self.corpo = corpo
        self.path = path
        super().__init__(f"Luma respondeu {status_code} em {path}: {corpo}")


class LumaClient:
    def __init__(self, api_key: str, *, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"x-luma-api-key": api_key},
            timeout=timeout,
        )
        self._ultima_chamada: float | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LumaClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def listar_eventos(self, **params: Any) -> Iterator[dict[str, Any]]:
        """GET /v1/calendars/events/list, paginado."""
        yield from self._paginar("/v1/calendars/events/list", params)

    def listar_guests(self, event_id: str, **params: Any) -> Iterator[dict[str, Any]]:
        """GET /v1/events/guests/list, paginado. Não traz detalhe de cupom."""
        yield from self._paginar("/v1/events/guests/list", {"event_id": event_id, **params})

    def obter_guest(self, event_id: str, guest_id: str) -> dict[str, Any]:
        """GET /v1/events/guests/get — único lugar com event_ticket_orders
        (cupom, amount_refunded). Uma chamada por guest, sem paginação."""
        return self._get("/v1/events/guests/get", {"event_id": event_id, "id": guest_id})

    # ------------------------------------------------------------------
    # Paginação: confia só em has_more. O Gate 1 achou next_cursor
    # preenchido mesmo quando has_more é false, então a mera presença do
    # cursor não pode decidir se pagina de novo.
    # ------------------------------------------------------------------

    def _paginar(self, path: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        params = dict(params)
        while True:
            corpo = self._get(path, params)
            yield from corpo.get("entries", [])

            if not corpo.get("has_more"):
                return

            cursor = corpo.get("next_cursor")
            if not cursor:
                return
            params["pagination_cursor"] = cursor

    # ------------------------------------------------------------------
    # HTTP + rate limit + retry
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        tentativa = 0
        while True:
            tentativa += 1
            self._pacear()
            resp = self._client.get(path, params=params or {})

            if resp.status_code == 429 or resp.status_code >= 500:
                if tentativa >= MAX_TENTATIVAS:
                    raise LumaAPIError(resp.status_code, self._corpo(resp), path)
                time.sleep(self._backoff(resp, tentativa))
                continue

            if resp.status_code >= 400:
                raise LumaAPIError(resp.status_code, self._corpo(resp), path)

            return resp.json()

    def _pacear(self) -> None:
        """Garante pelo menos INTERVALO_MIN_ENTRE_REQS segundos entre
        chamadas, pra ficar em torno de 150 req/min mesmo bem abaixo do
        teto real de 200."""
        agora = time.monotonic()
        if self._ultima_chamada is not None:
            espera = self._ultima_chamada + INTERVALO_MIN_ENTRE_REQS - agora
            if espera > 0:
                time.sleep(espera)
        self._ultima_chamada = time.monotonic()

    @staticmethod
    def _corpo(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            return resp.text

    @staticmethod
    def _backoff(resp: httpx.Response, tentativa: int) -> float:
        retry_after = resp.headers.get("retry-after")
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
        # A Luma manda Retry-After em todo 429 (confirmado no Gate 1). Isso
        # aqui é só um teto de segurança pra 5xx, que não manda o header.
        return min(2.0**tentativa, BACKOFF_TETO_SEGUNDOS)
