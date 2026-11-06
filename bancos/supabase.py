"""Supabase: autenticação do admin (Supabase Auth) e dados relacionais no PostgreSQL.

- Login: a senha é conferida pela API do Supabase Auth (GoTrue). Depois conferimos se o e-mail
  está na tabela "administradores" e se está ativo.
- Pedidos, itens, configurações e auditoria de login ficam em tabelas do PostgreSQL do Supabase.
"""
import json
from datetime import datetime, timezone

import requests
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool = None
_url = ""
_anon = ""
_service = ""


class ErroLogin(Exception):
    pass


def init(database_url, supabase_url="", anon_key="", service_key=""):
    global _pool, _url, _anon, _service
    _url, _anon, _service = supabase_url, anon_key, service_key
    if database_url:
        # prepare_threshold=None: compatível com o pooler do Supabase (PgBouncer).
        _pool = ConnectionPool(database_url, min_size=1, max_size=5, open=False, timeout=15,
                               kwargs={"row_factory": dict_row, "prepare_threshold": None,
                                       "connect_timeout": 10})
        _pool.open(wait=False)


def configurado():
    return _pool is not None


def modo_auth():
    """'supabase' quando a URL e a chave anon do projeto estão no .env; senão o modo local de desenvolvimento."""
    return "supabase" if _url and _anon else "local"


def _q(sql, params=None, um=False, todos=False):
    with _pool.connection() as conn:
        cur = conn.execute(sql, params or ())
        if um:
            return cur.fetchone()
        if todos:
            return cur.fetchall()
        return None


def ping():
    return _q("select current_database() as banco, version() as versao", um=True)


# ---------------------------------------------------------------- autenticação

def autenticar(email, senha):
    """Devolve o perfil do administrador ou levanta ErroLogin com uma mensagem para a tela."""
    email = (email or "").strip().lower()
    if not email or not senha:
        raise ErroLogin("Informe e-mail e senha.")

    if modo_auth() == "supabase":
        try:
            resposta = requests.post(
                f"{_url}/auth/v1/token?grant_type=password",
                headers={"apikey": _anon, "Content-Type": "application/json"},
                json={"email": email, "password": senha}, timeout=10)
        except requests.RequestException as erro:
            raise ErroLogin("Não foi possível falar com o Supabase. Tente de novo.") from erro
        if resposta.status_code != 200:
            raise ErroLogin("E-mail ou senha incorretos.")
        usuario = resposta.json().get("user") or {}
        admin = _q("""update administradores
                         set ultimo_acesso = now(), user_id = coalesce(user_id, %s::uuid)
                       where email = %s and ativo
                   returning id, nome, email""", (usuario.get("id"), email), um=True)
        if not admin:
            raise ErroLogin("Este usuário não tem acesso ao painel.")
        return {**admin, "id": str(admin["id"]), "via": "Supabase Auth"}

    # Modo local (sem as chaves do Supabase Auth): hash bcrypt conferido pelo pgcrypto no Postgres.
    admin = _q("""update administradores
                     set ultimo_acesso = now()
                   where email = %s and ativo and senha_hash is not null
                     and senha_hash = crypt(%s, senha_hash)
               returning id, nome, email""", (email, senha), um=True)
    if not admin:
        raise ErroLogin("E-mail ou senha incorretos.")
    return {**admin, "id": str(admin["id"]), "via": "PostgreSQL (pgcrypto)"}


def registrar_acesso(email, sucesso, motivo, ip):
    try:
        _q("insert into acessos_admin (email, sucesso, motivo, ip) values (%s, %s, %s, %s)",
           ((email or "").strip().lower()[:200] or "(vazio)", sucesso, motivo, ip))
    except Exception:  # a auditoria nunca deve impedir o login
        pass


def ultimos_acessos(limite=6):
    return _q("select email, sucesso, motivo, ip, criado_em from acessos_admin order by criado_em desc limit %s",
              (limite,), todos=True)


def criar_admin(email, nome, senha):
    """Usado por scripts/setup_supabase.py. Cria o usuário no Supabase Auth (se houver service key)
    e o perfil na tabela administradores."""
    email = email.strip().lower()
    user_id = None
    if _url and _service:
        r = requests.post(f"{_url}/auth/v1/admin/users",
                          headers={"apikey": _service, "Authorization": f"Bearer {_service}"},
                          json={"email": email, "password": senha, "email_confirm": True,
                                "user_metadata": {"nome": nome}}, timeout=15)
        if r.status_code in (200, 201):
            user_id = r.json().get("id")
        elif r.status_code == 422 or "already" in r.text.lower():
            user_id = None  # já existe no Auth; o vínculo é feito no primeiro login
        else:
            raise RuntimeError(f"Supabase Auth recusou a criação do usuário: {r.status_code} {r.text[:200]}")
    _q("""insert into administradores (email, nome, user_id, senha_hash)
          values (%s, %s, %s::uuid, crypt(%s, gen_salt('bf')))
          on conflict (email) do update
             set nome = excluded.nome, ativo = true,
                 user_id = coalesce(excluded.user_id, administradores.user_id),
                 senha_hash = excluded.senha_hash""", (email, nome, user_id, senha))
    return user_id


# ---------------------------------------------------------------- pedidos

def registrar_pedido(cliente, observacao, itens):
    """Chama a função PL/pgSQL que grava pedido + itens numa transação."""
    with _pool.connection() as conn:
        with conn.transaction():
            r = conn.execute("select * from registrar_pedido(%s, %s, %s::jsonb)",
                             (cliente, observacao, json.dumps(itens))).fetchone()
    return {"id": r["pedido_id"], "codigo": r["codigo"], "total": float(r["total"]),
            "qtd_itens": r["qtd_itens"]}


def salvar_mensagem(pedido_id, mensagem):
    _q("update pedidos set mensagem = %s where id = %s", (mensagem, pedido_id))


def listar_pedidos(limite=50, status=None):
    return _q("""
        select p.id, p.codigo, p.cliente_nome, p.observacao, p.total, p.qtd_itens, p.status,
               p.mensagem, p.criado_em,
               coalesce(json_agg(json_build_object(
                   'nome', i.nome, 'cor', i.cor, 'tamanho', i.tamanho, 'quantidade', i.quantidade,
                   'preco_unitario', i.preco_unitario, 'subtotal', i.subtotal, 'produto_id', i.produto_id)
                   order by i.id) filter (where i.id is not null), '[]') as itens
          from pedidos p
          left join itens_pedido i on i.pedido_id = p.id
         where (%s::text is null or p.status = %s::text)
         group by p.id
         order by p.criado_em desc
         limit %s""", (status, status, limite), todos=True)


def alterar_status(pedido_id, status):
    _q("update pedidos set status = %s where id = %s", (status, pedido_id))


def resumo_vendas():
    return _q("select * from vw_resumo_vendas", um=True)


# ---------------------------------------------------------------- configurações

def configuracoes():
    return {r["chave"]: r["valor"] for r in _q("select chave, valor from configuracoes", todos=True)}


def salvar_configuracoes(valores):
    with _pool.connection() as conn:
        with conn.transaction():
            for chave, valor in valores.items():
                conn.execute("""insert into configuracoes (chave, valor, atualizado_em) values (%s, %s, now())
                                on conflict (chave) do update set valor = excluded.valor, atualizado_em = now()""",
                             (chave, valor))


def agora():
    return datetime.now(timezone.utc)
