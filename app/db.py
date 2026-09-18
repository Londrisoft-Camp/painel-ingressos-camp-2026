"""Conexão com o Postgres (Supabase).

A API do painel fica no ar o tempo todo, atendendo requisições
concorrentes — usa a connection string pooled (Supavisor em modo
transaction, do Supabase), não a direta. Ver seção 4/Gate 0 do documento
de projeto.

prepare_threshold=None desliga os prepared statements automáticos do
psycopg3 nessa conexão. Em modo "transaction pooling", cada transação pode
cair num backend Postgres diferente por trás do pooler — um prepared
statement criado numa transação pode colidir com outro de mesmo nome já
existente noutro backend, estourando
`psycopg.errors.DuplicatePreparedStatement` (achado em produção, 18/09,
na migração de Neon para Supabase). Sem custo real aqui: as consultas do
painel são poucas e simples, o ganho de performance de preparar statement
não compensa a instabilidade.
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
    return psycopg.connect(database_url, prepare_threshold=None)
