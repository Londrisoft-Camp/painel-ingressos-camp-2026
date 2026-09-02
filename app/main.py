from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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


# Serve a TV estática (index.html na raiz, assets/ etc). Registrado por
# último de propósito: rotas de API definidas acima batem primeiro, o mount
# em "/" só pega o que sobrar.
STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
