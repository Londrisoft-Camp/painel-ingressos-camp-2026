"""Gate 6 — GET /api/painel bate com o shape da seção 7 do documento.

Roda contra o Neon real (só leitura, não escreve nada) — não mocka o
banco, é o mesmo espírito dos testes do Gate 5.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_api_painel_shape_e_regras():
    client = TestClient(app)
    resp = client.get("/api/painel")
    assert resp.status_code == 200

    body = resp.json()

    assert set(body.keys()) == {
        "fonte", "atualizadoEm", "semAtribuicao", "diasUteisRestantes", "csm", "comercial",
    }
    assert isinstance(body["semAtribuicao"], int)
    assert body["semAtribuicao"] >= 0
    assert isinstance(body["diasUteisRestantes"], int)
    assert body["diasUteisRestantes"] >= 0

    campos_time = {
        "meta", "realizado", "semanaAtual", "metaSemana", "realizadoSemana",
        "metaAcumulada", "realizadoAcumulado", "ritmoNecessario", "diferencaSemana", "statusSemana",
    }
    assert set(body["csm"].keys()) == campos_time | {"gerentes"}
    # Comercial não tem quebra individual -- decisão que reverteu o Gate 7 original.
    assert set(body["comercial"].keys()) == campos_time
    assert "gerentes" not in body["comercial"]

    assert len(body["csm"]["gerentes"]) == 4
    assert body["csm"]["meta"] == 300
    assert body["comercial"]["meta"] == 100

    assert len(body["csm"]["metaAcumulada"]) == 7
    assert len(body["csm"]["realizadoAcumulado"]) == 7
    assert 1 <= body["csm"]["semanaAtual"] <= 7
    assert body["csm"]["semanaAtual"] == body["comercial"]["semanaAtual"]

    for time in ("csm", "comercial"):
        assert body[time]["statusSemana"] in ("no_ritmo", "atencao", "atrasado")
        assert isinstance(body[time]["ritmoNecessario"], int)
        assert body[time]["ritmoNecessario"] >= 0
        # ritmo necessário é sempre o suficiente pra fechar a meta no prazo,
        # nunca uma fração otimista que deixa gap.
        faltam = max(body[time]["meta"] - body[time]["realizado"], 0)
        if body["diasUteisRestantes"] > 0:
            assert body[time]["ritmoNecessario"] * body["diasUteisRestantes"] >= faltam

    # Nenhum valor monetário em lugar nenhum do payload.
    payload_str = str(body)
    for termo_proibido in ("cents", "valor_bruto", "R$", "faturamento", "bonus"):
        assert termo_proibido not in payload_str
