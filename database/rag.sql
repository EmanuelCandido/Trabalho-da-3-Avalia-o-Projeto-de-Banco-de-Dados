-- =====================================================================
-- NOMA — banco vetorial (pgvector) para a busca semântica e o RAG
-- Rode depois do database/supabase.sql:
--     python scripts/setup_rag.py        (executa este arquivo)
-- ou cole no Supabase: SQL Editor > New query > Run.
-- Pode ser executado mais de uma vez sem duplicar nada.
--
-- O tamanho do vetor (768) precisa ser igual ao EMBEDDING_DIM do .env.
-- =====================================================================

-- No Supabase as extensões ficam no esquema "extensions".
create schema if not exists extensions;
create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------
-- Base de conhecimento vetorial: cada linha é um trecho de texto e o seu embedding.
--   fonte = 'produto'   -> o texto de um produto do MongoDB (referencia = _id do produto)
--   fonte = 'avaliacao' -> as avaliações de um produto juntas (referencia = _id do produto)
--   fonte = 'documento' -> um pedaço (chunk) de um documento da tabela documentos
-- O MongoDB continua sendo a fonte da verdade: esta tabela pode ser apagada e
-- reconstruída com: python scripts/indexar.py --tudo
-- ---------------------------------------------------------------------
create table if not exists public.conhecimento (
    id          bigserial primary key,
    fonte       text not null check (fonte in ('produto', 'avaliacao', 'documento')),
    referencia  text not null,
    trecho      integer not null default 0,
    titulo      text not null,
    conteudo    text not null,
    metadados   jsonb not null default '{}',
    hash        text not null,                  -- sha256 do conteúdo: só gera embedding se mudou
    modelo      text not null,                  -- ex.: gemini-embedding-001@768
    embedding   extensions.vector(768) not null,
    indexado_em timestamptz not null default now(),
    unique (fonte, referencia, trecho)
);

-- Índice HNSW para a distância de cosseno (operador <=>).
-- Não precisa de "treino" e pode ser criado com a tabela vazia (diferente do IVFFlat).
create index if not exists conhecimento_hnsw
    on public.conhecimento using hnsw (embedding extensions.vector_cosine_ops);
create index if not exists conhecimento_fonte_idx on public.conhecimento (fonte);

-- ---------------------------------------------------------------------
-- Documentos da base: políticas, guia de tamanhos, cuidados e uploads do admin.
-- ---------------------------------------------------------------------
create table if not exists public.documentos (
    id            uuid primary key default gen_random_uuid(),
    titulo        text not null,
    origem        text not null unique,          -- 'conhecimento/politicas.md' ou 'upload: Trocas.pdf'
    texto         text not null,
    caracteres    integer generated always as (char_length(texto)) stored,
    trechos       integer not null default 0,
    ativo         boolean not null default true,
    criado_em     timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Cada pergunta feita ao assistente, à busca semântica ou ao laboratório do painel.
-- ---------------------------------------------------------------------
create table if not exists public.interacoes_ia (
    id                  bigserial primary key,
    tipo                text not null check (tipo in ('chat', 'busca', 'laboratorio')),
    visitante           text,                     -- hash do visitante, nunca o IP
    pergunta            text not null,
    consulta            text,                     -- texto usado na busca vetorial
    trechos             jsonb not null default '[]',
    melhor_similaridade real,
    sem_resposta        boolean not null default false,
    resposta            text,
    modelo              text,
    tokens_entrada      integer,
    tokens_saida        integer,
    ms_embedding        integer,
    ms_busca            integer,
    ms_geracao          integer,
    avaliacao           smallint check (avaliacao in (-1, 1)),
    criado_em           timestamptz not null default now()
);
create index if not exists interacoes_ia_data_idx on public.interacoes_ia (criado_em desc);

-- ---------------------------------------------------------------------
-- Histórico das indexações (script, painel, n8n ou automática ao salvar um produto).
-- ---------------------------------------------------------------------
create table if not exists public.indexacoes (
    id                bigserial primary key,
    origem            text not null check (origem in ('script', 'painel', 'n8n', 'automatica')),
    escopo            text not null,
    trechos_novos     integer not null default 0,
    trechos_iguais    integer not null default 0,
    trechos_removidos integer not null default 0,
    ms                integer,
    status            text not null default 'ok',
    erro              text,
    criado_em         timestamptz not null default now()
);
create index if not exists indexacoes_data_idx on public.indexacoes (criado_em desc);

-- ---------------------------------------------------------------------
-- Busca por similaridade de cosseno.
-- O operador <=> devolve a DISTÂNCIA de cosseno; similaridade = 1 - distância.
-- O ORDER BY distância + LIMIT é o que permite ao Postgres usar o índice HNSW.
-- ---------------------------------------------------------------------
create or replace function public.buscar_conhecimento(
    p_embedding extensions.vector(768),
    p_qtd       integer default 6,
    p_fontes    text[]  default null
)
returns table (id bigint, fonte text, referencia text, trecho integer, titulo text, conteudo text,
               metadados jsonb, similaridade real)
language sql stable
as $$
    select c.id, c.fonte, c.referencia, c.trecho, c.titulo, c.conteudo, c.metadados,
           (1 - (c.embedding operator(extensions.<=>) p_embedding))::real as similaridade
      from public.conhecimento c
     where p_fontes is null or c.fonte = any (p_fontes)
     order by c.embedding operator(extensions.<=>) p_embedding
     limit least(greatest(p_qtd, 1), 20);
$$;

-- ---------------------------------------------------------------------
-- "Você também pode gostar": os produtos cujo vetor está mais perto do vetor do produto aberto.
-- Não chama a API de IA: usa o embedding que já está guardado.
-- ---------------------------------------------------------------------
create or replace function public.produtos_parecidos(p_referencia text, p_qtd integer default 4)
returns table (referencia text, similaridade real)
language sql stable
as $$
    select c.referencia,
           (1 - (c.embedding operator(extensions.<=>) a.embedding))::real as similaridade
      from public.conhecimento a
      join public.conhecimento c
        on c.fonte = 'produto' and c.trecho = 0 and c.referencia <> a.referencia
     where a.fonte = 'produto' and a.trecho = 0 and a.referencia = p_referencia
     order by c.embedding operator(extensions.<=>) a.embedding
     limit least(greatest(p_qtd, 1), 12);
$$;

-- ---------------------------------------------------------------------
-- Segurança: RLS ligado e sem políticas, como nas outras tabelas.
-- Ninguém lê pela API pública (chave anon); o servidor conecta direto no Postgres.
-- ---------------------------------------------------------------------
alter table public.conhecimento  enable row level security;
alter table public.documentos    enable row level security;
alter table public.interacoes_ia enable row level security;
alter table public.indexacoes    enable row level security;
