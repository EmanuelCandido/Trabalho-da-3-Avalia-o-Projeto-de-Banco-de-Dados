-- =====================================================================
-- NOMA — estrutura do Supabase (PostgreSQL)
-- Rode no Supabase: SQL Editor > New query > cole este arquivo > Run.
-- Ou rode: python scripts/setup_supabase.py (executa este arquivo e cria o admin).
-- O script pode ser executado mais de uma vez sem duplicar nada.
-- =====================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------
-- Administradores: quem pode entrar no painel.
-- A senha fica no Supabase Auth (auth.users); aqui guardamos o perfil.
-- senha_hash só é usada no modo de desenvolvimento local, sem Supabase Auth.
-- ---------------------------------------------------------------------
create table if not exists public.administradores (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid unique,
    email         text not null unique,
    nome          text not null,
    ativo         boolean not null default true,
    senha_hash    text,
    ultimo_acesso timestamptz,
    criado_em     timestamptz not null default now(),
    constraint email_minusculo check (email = lower(email))
);

-- No Supabase, liga o perfil ao usuário do Auth (fora dele, a tabela auth.users não existe).
do $$
begin
    if to_regclass('auth.users') is not null and not exists (
        select 1 from pg_constraint where conname = 'administradores_user_fk'
    ) then
        alter table public.administradores
            add constraint administradores_user_fk
            foreign key (user_id) references auth.users (id) on delete set null;
    end if;
end $$;

-- ---------------------------------------------------------------------
-- Auditoria de login: toda tentativa, certa ou errada.
-- ---------------------------------------------------------------------
create table if not exists public.acessos_admin (
    id        bigserial primary key,
    email     text not null,
    sucesso   boolean not null,
    motivo    text,
    ip        text,
    criado_em timestamptz not null default now()
);
create index if not exists acessos_admin_data_idx on public.acessos_admin (criado_em desc);

-- ---------------------------------------------------------------------
-- Pedidos enviados ao WhatsApp e seus itens.
-- produto_id guarda o _id do produto no MongoDB (referência entre bancos).
-- ---------------------------------------------------------------------
create table if not exists public.pedidos (
    id           bigserial primary key,
    codigo       text not null unique,
    cliente_nome text,
    observacao   text,
    total        numeric(10, 2) not null check (total >= 0),
    qtd_itens    integer not null check (qtd_itens > 0),
    mensagem     text,
    status       text not null default 'enviado_whatsapp'
                 check (status in ('enviado_whatsapp', 'confirmado', 'entregue', 'cancelado')),
    criado_em    timestamptz not null default now()
);
create index if not exists pedidos_data_idx on public.pedidos (criado_em desc);

create table if not exists public.itens_pedido (
    id             bigserial primary key,
    pedido_id      bigint not null references public.pedidos (id) on delete cascade,
    produto_id     text not null,
    nome           text not null,
    cor            text,
    tamanho        text,
    quantidade     integer not null check (quantidade > 0),
    preco_unitario numeric(10, 2) not null check (preco_unitario >= 0),
    subtotal       numeric(10, 2) generated always as (quantidade * preco_unitario) stored
);
create index if not exists itens_pedido_pedido_idx on public.itens_pedido (pedido_id);

-- ---------------------------------------------------------------------
-- Configurações da loja (editadas na tela Configurações do admin).
-- ---------------------------------------------------------------------
create table if not exists public.configuracoes (
    chave         text primary key,
    valor         text not null,
    atualizado_em timestamptz not null default now()
);

insert into public.configuracoes (chave, valor) values
    ('loja_nome', 'NOMA'),
    ('whatsapp_numero', ''),  -- vazio = usa WHATSAPP_NUMERO do .env
    ('faixa_promocional', '10% OFF EXTRA NO PIX'),
    ('faixa_termina_em', ''),  -- vazio: a contagem recomeça todo dia à meia-noite
    ('faixa_ativa', '1'),
    ('faixa_link', ''),
    ('faixa_contagem', '1'),
    ('faixa_cor_fundo', '#0b0b0c'),
    ('faixa_cor_texto', '#f2f2f2'),
    ('carrossel_tempo', '6'),
    ('carrossel_automatico', '1')
on conflict (chave) do nothing;

-- ---------------------------------------------------------------------
-- Função: grava o pedido e todos os itens numa única transação.
-- p_itens: [{"produto_id": "...", "nome": "...", "cor": "...", "tamanho": "...",
--            "quantidade": 1, "preco_unitario": 99.9}, ...]
-- ---------------------------------------------------------------------
create or replace function public.registrar_pedido(
    p_cliente    text,
    p_observacao text,
    p_itens      jsonb
)
returns table (pedido_id bigint, codigo text, total numeric, qtd_itens integer)
language plpgsql
as $$
declare
    v_id     bigint;
    v_codigo text;
    v_total  numeric(10, 2);
    v_qtd    integer;
begin
    if p_itens is null or jsonb_array_length(p_itens) = 0 then
        raise exception 'O pedido precisa de pelo menos um item';
    end if;

    select coalesce(sum((i ->> 'quantidade')::int * (i ->> 'preco_unitario')::numeric), 0),
           coalesce(sum((i ->> 'quantidade')::int), 0)
      into v_total, v_qtd
      from jsonb_array_elements(p_itens) as i;

    v_id := nextval(pg_get_serial_sequence('public.pedidos', 'id'));
    v_codigo := 'NOMA-' || lpad(v_id::text, 5, '0');

    insert into public.pedidos (id, codigo, cliente_nome, observacao, total, qtd_itens)
    values (v_id, v_codigo, nullif(trim(p_cliente), ''), nullif(trim(p_observacao), ''), v_total, v_qtd);

    insert into public.itens_pedido (pedido_id, produto_id, nome, cor, tamanho, quantidade, preco_unitario)
    select v_id, i ->> 'produto_id', i ->> 'nome', nullif(i ->> 'cor', ''), nullif(i ->> 'tamanho', ''),
           (i ->> 'quantidade')::int, (i ->> 'preco_unitario')::numeric
      from jsonb_array_elements(p_itens) as i;

    return query select v_id, v_codigo, v_total, v_qtd;
end;
$$;

-- ---------------------------------------------------------------------
-- View usada no dashboard do admin.
-- ---------------------------------------------------------------------
create or replace view public.vw_resumo_vendas as
select count(*)                                                    as pedidos,
       coalesce(sum(total), 0)::numeric(12, 2)                     as faturamento,
       coalesce(round(avg(total), 2), 0)::numeric(10, 2)           as ticket_medio,
       coalesce(sum(qtd_itens), 0)                                 as itens_vendidos,
       count(*) filter (where criado_em >= date_trunc('day', now())) as pedidos_hoje
  from public.pedidos
 where status <> 'cancelado';

-- ---------------------------------------------------------------------
-- Segurança: com RLS ligado e sem políticas, ninguém lê essas tabelas pela API
-- pública do Supabase (chave anon). O servidor Flask conecta direto no Postgres.
-- ---------------------------------------------------------------------
alter table public.administradores enable row level security;
alter table public.acessos_admin  enable row level security;
alter table public.pedidos        enable row level security;
alter table public.itens_pedido   enable row level security;
alter table public.configuracoes  enable row level security;
