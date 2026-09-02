"""
Gate 2 - Runner de migrations.

Aplica os arquivos .sql de /migrations em ordem alfabética, dentro de uma
transação por arquivo, e registra o que já rodou em schema_migration.
Rodar de novo não reaplica um arquivo já registrado.

Uso:
    python scripts/migrate.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


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

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print("ERRO: DATABASE_URL não definida (nem em .env nem no ambiente).", file=sys.stderr)
        sys.exit(1)
    return database_url


def garantir_tabela_controle(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists schema_migration (
                arquivo     text primary key,
                aplicado_em timestamptz not null default now()
            )
            """
        )
    conn.commit()


def ja_aplicado(conn: psycopg.Connection, arquivo: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select 1 from schema_migration where arquivo = %s", (arquivo,))
        return cur.fetchone() is not None


def aplicar(conn: psycopg.Connection, caminho: Path) -> None:
    sql = caminho.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute("insert into schema_migration (arquivo) values (%s)", (caminho.name,))
    conn.commit()


def main() -> None:
    database_url = carregar_env()
    arquivos = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not arquivos:
        print(f"Nenhum arquivo .sql encontrado em {MIGRATIONS_DIR}")
        sys.exit(1)

    with psycopg.connect(database_url) as conn:
        garantir_tabela_controle(conn)

        for caminho in arquivos:
            if ja_aplicado(conn, caminho.name):
                print(f"pulando (já aplicado): {caminho.name}")
                continue
            print(f"aplicando: {caminho.name}")
            try:
                aplicar(conn, caminho)
            except Exception:
                conn.rollback()
                raise
            print("  ok")

    print("Migrations em dia.")


if __name__ == "__main__":
    main()
