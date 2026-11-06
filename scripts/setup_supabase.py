"""Cria as tabelas no Supabase (database/supabase.sql) e o usuário administrador.

Uso:
    python scripts/setup_supabase.py
    python scripts/setup_supabase.py --email admin@noma.com --nome "Admin NOMA"

A senha é pedida no terminal (ou lida de ADMIN_SENHA). Com SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no .env,
o usuário também é criado no Supabase Auth; sem eles, use Authentication > Users > Add user no painel.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import psycopg  # noqa: E402

from bancos import supabase  # noqa: E402
from config import Config  # noqa: E402


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--email", default=os.getenv("ADMIN_EMAIL"))
    args.add_argument("--nome", default=os.getenv("ADMIN_NOME", "Administrador NOMA"))
    args.add_argument("--so-tabelas", action="store_true", help="só cria as tabelas, sem o admin")
    opcoes = args.parse_args()

    if not Config.DATABASE_URL:
        sys.exit("Preencha DATABASE_URL no .env (Supabase > Project Settings > Database > Connection string).")

    sql = (RAIZ / "database" / "supabase.sql").read_text(encoding="utf-8")
    with psycopg.connect(Config.DATABASE_URL, prepare_threshold=None, autocommit=True) as conn:
        conn.execute(sql)
    print("Tabelas, função registrar_pedido e view vw_resumo_vendas criadas.")
    if opcoes.so_tabelas:
        return

    email = opcoes.email or input("E-mail do administrador: ").strip()
    senha = os.getenv("ADMIN_SENHA") or getpass.getpass("Senha (mín. 8 caracteres): ")
    if len(senha) < 8:
        sys.exit("A senha precisa ter pelo menos 8 caracteres.")

    supabase.init(Config.DATABASE_URL, Config.SUPABASE_URL, Config.SUPABASE_ANON_KEY,
                  Config.SUPABASE_SERVICE_ROLE_KEY)
    user_id = supabase.criar_admin(email, opcoes.nome, senha)
    if Config.SUPABASE_SERVICE_ROLE_KEY:
        print(f"Administrador {email} criado no Supabase Auth" + (f" (id {user_id})." if user_id else " (já existia)."))
    else:
        print(f"Perfil de {email} criado na tabela administradores.")
        print("Sem SUPABASE_SERVICE_ROLE_KEY: crie o mesmo e-mail em Authentication > Users > Add user.")


if __name__ == "__main__":
    main()
