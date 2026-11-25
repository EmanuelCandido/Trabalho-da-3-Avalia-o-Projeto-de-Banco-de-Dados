"""Prepara o banco vetorial no Supabase: extensão pgvector, tabelas, índice HNSW e funções (database/rag.sql).

Uso:
    python scripts/setup_rag.py

O tamanho do vetor vem do EMBEDDING_DIM do .env (padrão 768). Pode rodar mais de uma vez.
Depois: python scripts/indexar.py --tudo
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import psycopg  # noqa: E402

from config import Config  # noqa: E402


def main():
    if not Config.DATABASE_URL:
        sys.exit("Preencha DATABASE_URL no .env (Supabase > Project Settings > Database > Connection string).")
    dim = Config.EMBEDDING_DIM
    if dim > 2000:
        sys.exit("O índice HNSW do tipo vector aceita até 2000 dimensões. Use EMBEDDING_DIM=768 (ou 1536).")

    sql = (RAIZ / "database" / "rag.sql").read_text(encoding="utf-8").replace("vector(768)", f"vector({dim})")
    with psycopg.connect(Config.DATABASE_URL, prepare_threshold=None, autocommit=True) as conn:
        atual = conn.execute("""select format_type(a.atttypid, a.atttypmod)
                                  from pg_attribute a
                                 where a.attrelid = to_regclass('public.conhecimento') and a.attname = 'embedding'
                             """).fetchone()
        if atual and f"({dim})" not in atual[0]:
            sys.exit(f"A coluna conhecimento.embedding já existe como {atual[0]}, diferente de EMBEDDING_DIM={dim}.\n"
                     "Para trocar o tamanho, apague a tabela (drop table public.conhecimento) e rode de novo.")
        conn.execute(sql)
        versao = conn.execute("select extversion from pg_extension where extname = 'vector'").fetchone()[0]
        tabelas = conn.execute("""select string_agg(tablename, ', ' order by tablename) from pg_tables
                                   where schemaname = 'public'
                                     and tablename in ('conhecimento', 'documentos', 'interacoes_ia', 'indexacoes')
                               """).fetchone()[0]
    print(f"pgvector {versao} ativo.")
    print(f"Tabelas: {tabelas}.")
    print(f"Índice HNSW e funções buscar_conhecimento e produtos_parecidos criados (vetores de {dim} dimensões).")
    print("Próximo passo: python scripts/indexar.py --tudo")


if __name__ == "__main__":
    main()
