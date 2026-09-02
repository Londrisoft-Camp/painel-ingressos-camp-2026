"""Testes do sync/luma.py — Gate 3.

Tudo mockado via respx (não bate na API real). O que precisa provar:
backoff real em 429, esgotamento de tentativas, paginação que confia só em
has_more (não no next_cursor residual), e erro real propagado sem contorno
(403 pra evento sem acesso, não um 404 genérico).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from sync.luma import LumaAPIError, LumaClient

EVENTS_URL = "https://public-api.luma.com/v1/calendars/events/list"
GUESTS_URL = "https://public-api.luma.com/v1/events/guests/list"


@respx.mock
def test_backoff_em_429_respeita_retry_after(monkeypatch):
    esperas = []
    monkeypatch.setattr("sync.luma.time.sleep", lambda s: esperas.append(s))

    rota = respx.get(EVENTS_URL)
    rota.side_effect = [
        httpx.Response(429, headers={"retry-after": "2"}, json={"message": "rate limited", "code": None}),
        httpx.Response(200, json={"entries": [{"id": "evt-1"}], "has_more": False}),
    ]

    with LumaClient(api_key="chave-teste") as client:
        eventos = list(client.listar_eventos())

    assert eventos == [{"id": "evt-1"}]
    assert rota.call_count == 2
    assert 2.0 in esperas


@respx.mock
def test_esgota_tentativas_e_levanta_erro(monkeypatch):
    monkeypatch.setattr("sync.luma.time.sleep", lambda s: None)

    rota = respx.get(EVENTS_URL)
    rota.mock(return_value=httpx.Response(429, headers={"retry-after": "1"}, json={"message": "rate limited"}))

    with LumaClient(api_key="chave-teste") as client:
        with pytest.raises(LumaAPIError) as exc_info:
            list(client.listar_eventos())

    assert exc_info.value.status_code == 429
    assert rota.call_count == 5


@respx.mock
def test_backoff_tambem_em_5xx_sem_retry_after(monkeypatch):
    esperas = []
    monkeypatch.setattr("sync.luma.time.sleep", lambda s: esperas.append(s))

    rota = respx.get(EVENTS_URL)
    rota.side_effect = [
        httpx.Response(503, json={"message": "temporariamente indisponível"}),
        httpx.Response(200, json={"entries": [], "has_more": False}),
    ]

    with LumaClient(api_key="chave-teste") as client:
        list(client.listar_eventos())

    assert rota.call_count == 2
    # 2 ** tentativa(1) do backoff exponencial — pode ter mais uma espera
    # pequena do próprio paceamento entre chamadas, isso é esperado.
    assert 2.0 in esperas


@respx.mock
def test_paginacao_confia_em_has_more_ignora_next_cursor_residual(monkeypatch):
    monkeypatch.setattr("sync.luma.time.sleep", lambda s: None)

    rota = respx.get(GUESTS_URL)
    rota.mock(
        return_value=httpx.Response(
            200,
            json={
                "entries": [{"id": "gst-1"}],
                "has_more": False,
                # next_cursor presente mesmo com has_more false — achado real do Gate 1
                "next_cursor": "cursor-fantasma",
            },
        )
    )

    with LumaClient(api_key="chave-teste") as client:
        guests = list(client.listar_guests(event_id="evt-1"))

    assert guests == [{"id": "gst-1"}]
    assert rota.call_count == 1


@respx.mock
def test_paginacao_segue_enquanto_has_more_for_true(monkeypatch):
    monkeypatch.setattr("sync.luma.time.sleep", lambda s: None)

    rota = respx.get(GUESTS_URL)
    rota.side_effect = [
        httpx.Response(200, json={"entries": [{"id": "gst-1"}], "has_more": True, "next_cursor": "abc"}),
        httpx.Response(200, json={"entries": [{"id": "gst-2"}], "has_more": False}),
    ]

    with LumaClient(api_key="chave-teste") as client:
        guests = list(client.listar_guests(event_id="evt-1"))

    assert guests == [{"id": "gst-1"}, {"id": "gst-2"}]
    assert rota.call_count == 2
    segunda_chamada = rota.calls[1].request
    assert "pagination_cursor=abc" in str(segunda_chamada.url)


@respx.mock
def test_erro_evento_sem_acesso_e_403_nao_e_contornado(monkeypatch):
    monkeypatch.setattr("sync.luma.time.sleep", lambda s: None)

    respx.get(GUESTS_URL).mock(
        return_value=httpx.Response(403, json={"message": "You don't have access to this event.", "code": None})
    )

    with LumaClient(api_key="chave-teste") as client:
        with pytest.raises(LumaAPIError) as exc_info:
            list(client.listar_guests(event_id="evt-naoexiste"))

    assert exc_info.value.status_code == 403
    assert "access" in str(exc_info.value.corpo)


@respx.mock
def test_pacing_espera_entre_chamadas_consecutivas(monkeypatch):
    valores = iter([1000.0, 1000.0, 1000.05, 1000.05])
    monkeypatch.setattr("sync.luma.time.monotonic", lambda: next(valores))
    esperas = []
    monkeypatch.setattr("sync.luma.time.sleep", lambda s: esperas.append(s))

    respx.get(EVENTS_URL).mock(return_value=httpx.Response(200, json={"entries": [], "has_more": False}))

    with LumaClient(api_key="chave-teste") as client:
        list(client.listar_eventos())
        list(client.listar_eventos())

    # 1a chamada não espera (não há chamada anterior). 2a espera porque
    # veio 0.05s depois da 1a, e o intervalo mínimo pra ~150 req/min é 0.4s.
    assert len(esperas) == 1
    assert esperas[0] == pytest.approx(0.35, abs=0.01)
