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

    assert set(body.keys()) == {"fonte", "atualizadoEm", "semAtribuicao", "csm", "comercial"}
    assert isinstance(body["semAtribuicao"], int)
    assert body["semAtribuicao"] >= 0

    assert set(body["csm"].keys()) == {
        "meta", "realizado", "semanaAtual", "metaSemana", "realizadoSemana",
        "metaAcumulada", "realizadoAcumulado", "gerentes",
    }
    # Comercial não tem quebra individual -- decisão que reverteu o Gate 7 original.
    assert set(body["comercial"].keys()) == {
        "meta", "realizado", "semanaAtual", "metaSemana", "realizadoSemana",
        "metaAcumulada", "realizadoAcumulado",
    }
    assert "gerentes" not in body["comercial"]

    assert len(body["csm"]["gerentes"]) == 4
    assert body["csm"]["meta"] == 300
    assert body["comercial"]["meta"] == 100

    assert len(body["csm"]["metaAcumulada"]) == 7
    assert len(body["csm"]["realizadoAcumulado"]) == 7
    assert 1 <= body["csm"]["semanaAtual"] <= 7
    assert body["csm"]["semanaAtual"] == body["comercial"]["semanaAtual"]

    # Nenhum valor monetário em lugar nenhum do payload.
    payload_str = str(body)
    for termo_proibido in ("cents", "valor_bruto", "R$", "faturamento", "bonus"):
        assert termo_proibido not in payload_str
