"""Banco vetorial: pgvector no PostgreSQL do Supabase (tabelas do database/rag.sql).

- conhecimento: trechos de texto e seus embeddings (produtos, avaliações e documentos)
- documentos:   textos da base (políticas, guia de tamanhos, uploads do admin)
- interacoes_ia e indexacoes: histórico do que foi perguntado e indexado

Os vetores vão para o Postgres como texto '[0.12,-0.03,...]' convertido com ::vector.
"""
import re

from psycopg.types.json import Jsonb

from bancos import supabase

TIPO_VETOR = "extensions.vector"


def vetor_sql(valores):
    """Lista de floats -> literal do pgvector."""
    return "[" + ",".join(f"{v:.7f}" for v in valores) + "]"


def _q(sql, params=None, um=False, todos=False):
    with supabase.conexao() as conn:
        cur = conn.execute(sql, params or ())
        if um:
            return cur.fetchone()
        if todos:
            return cur.fetchall()
        return cur.rowcount


# ---------------------------------------------------------------- conhecimento (vetores)

def hashes(fontes, referencias=None):
    """{(fonte, referencia, trecho): (hash, modelo)} do que já está indexado."""
    linhas = _q("""select fonte, referencia, trecho, hash, modelo from conhecimento
                    where fonte = any(%s::text[]) and (%s::text[] is null or referencia = any(%s::text[]))""",
                (list(fontes), referencias, referencias), todos=True)
    return {(r["fonte"], r["referencia"], r["trecho"]): (r["hash"], r["modelo"]) for r in linhas}


def gravar_trechos(trechos):
    """Insere ou atualiza (upsert) cada trecho com o seu embedding."""
    if not trechos:
        return 0
    with supabase.conexao() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.executemany(f"""
                    insert into conhecimento (fonte, referencia, trecho, titulo, conteudo, metadados, hash,
                                              modelo, embedding, indexado_em)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s::{TIPO_VETOR}, now())
                    on conflict (fonte, referencia, trecho) do update
                       set titulo = excluded.titulo, conteudo = excluded.conteudo,
                           metadados = excluded.metadados, hash = excluded.hash, modelo = excluded.modelo,
                           embedding = excluded.embedding, indexado_em = now()""",
                    [(t["fonte"], t["referencia"], t["trecho"], t["titulo"], t["conteudo"], Jsonb(t["metadados"]),
                      t["hash"], t["modelo"], vetor_sql(t["embedding"])) for t in trechos])
    return len(trechos)


def remover_chaves(chaves):
    """Apaga trechos pelas chaves (fonte, referencia, trecho)."""
    total = 0
    with supabase.conexao() as conn:
        with conn.transaction():
            for fonte, referencia, trecho in chaves:
                total += conn.execute("delete from conhecimento where fonte = %s and referencia = %s and trecho = %s",
                                      (fonte, referencia, trecho)).rowcount
    return total


def remover_referencias(fontes, referencias):
    """Apaga tudo de algumas referências (ex.: produto excluído ou desativado)."""
    if not referencias:
        return 0
    return _q("delete from conhecimento where fonte = any(%s::text[]) and referencia = any(%s::text[])",
              (list(fontes), list(referencias)))


def remover_fora_de(fontes, referencias_validas):
    """Apaga as referências que não existem mais na origem (órfãs)."""
    return _q("delete from conhecimento where fonte = any(%s::text[]) and not (referencia = any(%s::text[]))",
              (list(fontes), list(referencias_validas)))


def buscar(embedding, qtd=6, fontes=None):
    """Os trechos mais parecidos com o vetor da pergunta (função buscar_conhecimento do rag.sql)."""
    return _q(f"select * from buscar_conhecimento(%s::{TIPO_VETOR}, %s, %s)",
              (vetor_sql(embedding), qtd, list(fontes) if fontes else None), todos=True)


def parecidos(referencia, qtd=4):
    """Produtos mais próximos do vetor do produto informado (sem chamar a API de IA)."""
    return _q("select * from produtos_parecidos(%s, %s)", (referencia, qtd), todos=True)


def contar():
    return _q("select count(*) as n from conhecimento", um=True)["n"]


def estatisticas():
    por_fonte = {r["fonte"]: r["qtd"] for r in
                 _q("select fonte, count(*) as qtd from conhecimento group by fonte", todos=True)}
    modelos = [r["modelo"] for r in _q("select distinct modelo from conhecimento order by 1", todos=True)]
    ultima = _q("select * from indexacoes order by criado_em desc limit 1", um=True)
    return {"por_fonte": por_fonte, "total": sum(por_fonte.values()), "modelos": modelos, "ultima": ultima}


# ---------------------------------------------------------------- documentos da base

def salvar_documento(titulo, origem, texto):
    """Cria ou atualiza pelo campo origem. Devolve o id."""
    r = _q("""insert into documentos (titulo, origem, texto) values (%s, %s, %s)
              on conflict (origem) do update
                 set titulo = excluded.titulo, texto = excluded.texto, atualizado_em = now()
               where documentos.titulo is distinct from excluded.titulo
                  or documentos.texto is distinct from excluded.texto
           returning id""", (titulo, origem, texto), um=True)
    if r:
        return str(r["id"])
    return str(_q("select id from documentos where origem = %s", (origem,), um=True)["id"])


def listar_documentos(so_ativos=False):
    return _q("""select id, titulo, origem, texto, caracteres, trechos, ativo, criado_em, atualizado_em
                   from documentos where (not %s or ativo) order by titulo""", (so_ativos,), todos=True)


def documento(documento_id):
    return _q("select * from documentos where id = %s::uuid", (documento_id,), um=True)


def definir_trechos_documento(documento_id, quantidade):
    _q("update documentos set trechos = %s where id = %s::uuid", (quantidade, documento_id))


def documento_da_origem(origem):
    return _q("select id from documentos where origem = %s", (origem,), um=True)


def editar_documento(documento_id, titulo, texto):
    return _q("update documentos set titulo = %s, texto = %s, atualizado_em = now() where id = %s::uuid",
              (titulo, texto, documento_id))


def excluir_documento(documento_id):
    remover_referencias(["documento"], [str(documento_id)])
    return _q("delete from documentos where id = %s::uuid", (documento_id,))


def alternar_documento(documento_id):
    r = _q("update documentos set ativo = not ativo, atualizado_em = now() where id = %s::uuid returning ativo",
           (documento_id,), um=True)
    return r["ativo"] if r else None


# ---------------------------------------------------------------- números do painel

FUSO = "America/Sao_Paulo"


def sobre_o_banco():
    """Versão do pgvector e tamanho da tabela e do índice HNSW."""
    return _q("""select (select extversion from pg_extension where extname = 'vector') as pgvector,
                        pg_size_pretty(pg_table_size('public.conhecimento')) as tabela,
                        pg_size_pretty(pg_relation_size('public.conhecimento_hnsw')) as hnsw""", um=True)


def ultimas_indexacoes(limite=8):
    return _q("select * from indexacoes order by criado_em desc limit %s", (limite,), todos=True)


def numeros_das_perguntas(dias=7):
    """Perguntas de clientes (chat e busca); as do laboratório ficam de fora."""
    return _q(f"""select count(*) filter (where hoje) as hoje, count(*) as total,
                         count(*) filter (where tipo = 'chat') as chat, count(*) filter (where tipo = 'busca') as busca,
                         count(*) filter (where sem_resposta) as sem_resposta,
                         count(*) filter (where avaliacao = 1) as positivas,
                         count(*) filter (where avaliacao = -1) as negativas,
                         round(avg(ms_embedding + ms_busca + ms_geracao) filter (where ms_geracao is not null))::int
                             as ms_medio
                    from (select *, criado_em at time zone '{FUSO}' >= date_trunc('day', now() at time zone '{FUSO}')
                                 as hoje
                            from interacoes_ia
                           where tipo in ('chat', 'busca') and criado_em > now() - make_interval(days => %s)) i""",
              (dias,), um=True)


def listar_interacoes(filtro="todas", tipo=None, limite=50, pular=0):
    condicao = {"sem-resposta": "and sem_resposta", "negativas": "and avaliacao = -1"}.get(filtro, "")
    return _q(f"""select id, tipo, pergunta, consulta, trechos, melhor_similaridade, sem_resposta, resposta, modelo,
                         tokens_entrada, tokens_saida, ms_embedding, ms_busca, ms_geracao, avaliacao, criado_em
                    from interacoes_ia
                   where tipo in ('chat', 'busca') and (%s::text is null or tipo = %s) {condicao}
                   order by criado_em desc limit %s offset %s""", (tipo, tipo, limite, pular), todos=True)


def plano(embedding, forcar_indice=False, qtd=6):
    """EXPLAIN ANALYZE da busca por similaridade. SET LOCAL vale só dentro da transação: o pooler do Supabase
    (modo transação) entrega a conexão para outra pessoa logo depois."""
    with supabase.conexao() as conn:
        with conn.transaction():
            if forcar_indice:
                conn.execute("set local enable_seqscan = off")
                conn.execute("set local enable_sort = off")
            linhas = conn.execute(
                f"""explain (analyze, costs off, timing on, summary on)
                    select id, 1 - (embedding operator(extensions.<=>) %s::{TIPO_VETOR}) as similaridade
                      from conhecimento
                     order by embedding operator(extensions.<=>) %s::{TIPO_VETOR} limit {int(qtd)}""",
                (vetor_sql(embedding), vetor_sql(embedding))).fetchall()
    # o vetor aparece inteiro no plano (768 números): corta para dar para ler
    return [re.sub(r"'\[[^\]]{40,}\]'", "'[…768 números…]'", r["QUERY PLAN"]) for r in linhas]


# ---------------------------------------------------------------- histórico

def registrar_indexacao(origem, escopo, novos=0, iguais=0, removidos=0, ms=None, status="ok", erro=None):
    try:
        _q("""insert into indexacoes (origem, escopo, trechos_novos, trechos_iguais, trechos_removidos, ms, status, erro)
              values (%s, %s, %s, %s, %s, %s, %s, %s)""",
           (origem, escopo, novos, iguais, removidos, ms, status, (erro or "")[:500] or None))
    except Exception:  # o histórico nunca deve impedir a indexação
        pass


def registrar_interacao(**campos):
    """Grava uma pergunta (chat, busca ou laboratório) e devolve o id."""
    colunas = ["tipo", "visitante", "pergunta", "consulta", "trechos", "melhor_similaridade", "sem_resposta",
               "resposta", "modelo", "tokens_entrada", "tokens_saida", "ms_embedding", "ms_busca", "ms_geracao"]
    valores = [Jsonb(campos.get(c) or []) if c == "trechos" else campos.get(c) for c in colunas]
    if valores[6] is None:
        valores[6] = False
    try:
        r = _q(f"insert into interacoes_ia ({', '.join(colunas)}) values ({', '.join(['%s'] * len(colunas))}) "
               "returning id", valores, um=True)
        return r["id"]
    except Exception:
        return None


def avaliar_interacao(interacao_id, visitante, nota):
    """👍 (1) ou 👎 (-1), só de quem fez a pergunta."""
    return _q("update interacoes_ia set avaliacao = %s where id = %s and visitante = %s",
              (nota, interacao_id, visitante)) == 1


def trechos_de(referencia, embedding):
    """Todos os trechos de uma referência (ex.: o produto aberto quando o chat começou na página dele),
    com a similaridade em relação à pergunta."""
    return _q(f"""select id, fonte, referencia, trecho, titulo, conteudo, metadados,
                         (1 - (embedding operator(extensions.<=>) %s::{TIPO_VETOR}))::real as similaridade
                    from conhecimento where referencia = %s order by fonte, trecho""",
              (vetor_sql(embedding), referencia), todos=True)


SQL_BUSCA = """select id, fonte, titulo,
       1 - (embedding <=> :vetor_da_pergunta) as similaridade
  from conhecimento
 order by embedding <=> :vetor_da_pergunta   -- distância de cosseno (índice HNSW)
 limit {qtd};"""
