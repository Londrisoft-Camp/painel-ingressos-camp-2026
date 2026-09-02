"""Conexão com o Neon.

A API do painel fica no ar o tempo todo, atendendo requisições
concorrentes — usa a connection string pooled (PgBouncer do Neon), não a
direta. Ver seção 4/Gate 0 do documento de projeto.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg


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


def conectar() -> psycopg.Connection:
    carregar_env()
    database_url = os.environ["DATABASE_URL_POOLED"]
    return psycopg.connect(database_url)
