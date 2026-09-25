from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

from app.consulta import buscar, listar_vendedores
from app.db import conectar
from app.painel import montar_payload

app = FastAPI(title="Painel de Ingressos - Londrisoft Camp 2026")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/painel")
def api_painel():
    with conectar() as conn:
        return montar_payload(conn)


@app.get("/api/vendedores")
def api_vendedores():
    with conectar() as conn:
        return listar_vendedores(conn)


@app.get("/api/consulta")
def api_consulta(busca: str = Query(min_length=3), vendedor_id: int = Query()):
    with conectar() as conn:
        return buscar(conn, busca, vendedor_id)


# Serve a TV estática (index.html na raiz, assets/ etc). Registrado por
# último de propósito: rotas de API definidas acima batem primeiro, o mount
# em "/" só pega o que sobrar.
STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
