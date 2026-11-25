"""Painel > Assistente IA: visão geral do banco vetorial, laboratório de RAG, documentos da base e perguntas.

    GET  /admin/assistente                            visão geral
    POST /admin/assistente/reindexar                  sincroniza catálogo e documentos com o pgvector
    GET  /admin/assistente/laboratorio                cada etapa do RAG, uma por uma
    POST /admin/assistente/laboratorio/perguntar      {pergunta} -> vetor, candidatos, prompt, resposta e tempos
    POST /admin/assistente/laboratorio/sem-rag        {pergunta} -> a mesma pergunta direto ao modelo
    POST /admin/assistente/laboratorio/comparar       {pergunta} -> busca por texto x busca vetorial
    POST /admin/assistente/laboratorio/plano          {pergunta} -> EXPLAIN ANALYZE com e sem o índice HNSW
    GET  /admin/assistente/documentos                 lista, envio, edição e trechos
    GET  /admin/assistente/perguntas                  o que os clientes perguntaram
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePath
from urllib.parse import urlsplit
from uuid import UUID

import psycopg
import requests
from flask import Blueprint, current_app, jsonify, render_template, request

from bancos import mongo, redis_store, vetorial
from ia import busca, gemini, indexador, rag, textos
from utils import admin_obrigatorio, brl, miniatura

bp = Blueprint("admin_ia", __name__, url_prefix="/admin/assistente")
log = logging.getLogger("noma.ia")

EXTENSOES = {".md", ".txt", ".pdf"}
MAX_ARQUIVO = 2 * 1024 * 1024      # a Vercel aceita até 4,5 MB por requisição
MAX_TEXTO = 60_000                 # ~80 trechos: cabe num lote de embeddings do plano gratuito
MAX_PERGUNTA = 500
POR_PAGINA = 50
FILTROS_PERGUNTAS = {"todas": "Todas", "sem-resposta": "Sem resposta", "negativas": "Não ajudaram"}
PASTA = "conhecimento/"            # documentos que vêm dos arquivos do repositório


@bp.errorhandler(psycopg.Error)
def banco_fora(erro):
    log.exception("Falha no banco vetorial: %s", erro)
    if request.method == "POST" or request.headers.get("X-Requested-With") == "fetch":
        return jsonify(erro="O Supabase não respondeu. Tente de novo."), 503
    return render_template("loja/erro.html", codigo=503, titulo="Estamos com uma instabilidade",
                           texto="O Supabase não respondeu. Tente de novo em instantes."), 503


# ---------------------------------------------------------------- visão geral

def _status_n8n(url):
    """{'configurado', 'ok'}: o n8n tem uma rota de saúde em /healthz."""
    if not url:
        return {"configurado": False, "ok": False}
    partes = urlsplit(url)
    try:
        return {"configurado": True,
                "ok": requests.get(f"{partes.scheme}://{partes.netloc}/healthz", timeout=1.5).ok}
    except requests.RequestException:
        return {"configurado": True, "ok": False}


def _status_gemini():
    if not gemini.ativo():
        return {"configurado": False, "ok": False}
    try:
        return {"configurado": True, "ok": True, "ms": gemini.ping()}
    except gemini.ErroIA as erro:
        return {"configurado": True, "ok": False, "erro": str(erro)[:200]}


def _uso_do_dia(limite_chat, limite_busca):
    try:
        return {"chat": redis_store.cota_usada("chat"), "busca": redis_store.cota_usada("busca"),
                "limite_chat": limite_chat, "limite_busca": limite_busca}
    except Exception:
        return None


def _pendencias():
    try:
        return indexador.pendencias()
    except Exception:
        log.exception("Não foi possível comparar o índice com o MongoDB")
        return None


def visao_geral():
    """Cada parte é uma ida a um serviço diferente (Supabase, MongoDB, Redis, Gemini, n8n): vão todas juntas."""
    cfg = current_app.config
    tarefas = {"indice": vetorial.estatisticas, "banco": vetorial.sobre_o_banco, "pendentes": _pendencias,
               "perguntas": vetorial.numeros_das_perguntas, "indexacoes": lambda: vetorial.ultimas_indexacoes(8),
               "uso": lambda: _uso_do_dia(cfg["IA_LIMITE_DIA"], cfg["IA_LIMITE_BUSCA_DIA"]),
               "gemini": _status_gemini, "n8n": lambda: _status_n8n(cfg.get("N8N_WEBHOOK_URL") or "")}
    with ThreadPoolExecutor(max_workers=len(tarefas)) as grupo:
        futuros = {nome: grupo.submit(f) for nome, f in tarefas.items()}
        dados = {nome: f.result() for nome, f in futuros.items()}
    modelo = gemini.modelo_embedding()
    return {**dados, "modelo_embedding": modelo, "modelo": gemini.modelo(), "dimensoes": gemini.dimensoes(),
            "limiar": busca.LIMIAR, "top_k": busca.TOP_K,
            "outro_modelo": [m for m in dados["indice"]["modelos"] if m != modelo]}  # vetores que não se comparam


def _sem_tabelas(erro):
    """O database/rag.sql ainda não foi rodado neste banco."""
    return isinstance(erro, (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedFunction))


def _nomes_dos_escopos(indexacoes):
    """'produto:6aee…' vira o nome do produto; 'documento:<uuid>' vira o título do documento."""
    produtos = {p["id"]: p["nome"] for p in mongo.por_ids(
        [i["escopo"].split(":", 1)[1] for i in indexacoes if i["escopo"].startswith("produto:")])}
    documentos = {str(d["id"]): d["titulo"] for d in vetorial.listar_documentos()}
    fixos = {"catalogo": "Catálogo inteiro", "documentos": "Todos os documentos", "tudo": "Catálogo e documentos"}
    for i in indexacoes:
        tipo, _, ref = i["escopo"].partition(":")
        i["nome"] = fixos.get(i["escopo"]) or (produtos.get(ref) if tipo == "produto" else documentos.get(ref))             or ("Produto excluído" if tipo == "produto" else "Documento excluído")
    return indexacoes


@bp.get("")
@admin_obrigatorio
def inicio():
    try:
        dados = visao_geral()
    except psycopg.Error as erro:
        if _sem_tabelas(erro):
            return render_template("admin/assistente.html", sem_tabelas=True)
        raise
    try:
        _nomes_dos_escopos(dados["indexacoes"])
    except Exception:
        log.exception("Nomes do histórico de indexações")
    return render_template("admin/assistente.html", **dados)


@bp.post("/reindexar")
@admin_obrigatorio
def reindexar():
    """Catálogo e documentos. A pasta conhecimento/ só é importada pelo scripts/indexar.py."""
    if not gemini.ativo():
        return jsonify(erro="Preencha GEMINI_API_KEY no .env para indexar."), 409
    try:
        catalogo = indexador.indexar_catalogo("painel")
        documentos = indexador.indexar_documentos("painel")
    except gemini.ErroIA as erro:
        log.warning("Reindexação pelo painel falhou: %s", erro)
        return jsonify(erro="O Gemini não respondeu. Os trechos que não mudaram continuam no índice."), 503
    return jsonify({k: catalogo[k] + documentos[k] for k in ("novos", "iguais", "removidos", "ms")})


# ---------------------------------------------------------------- laboratório

def _pergunta():
    """(pergunta, resposta de erro). As quatro ações do laboratório validam do mesmo jeito."""
    bruto = (request.get_json(silent=True) or {}).get("pergunta")
    texto = " ".join(bruto.split()) if isinstance(bruto, str) else ""
    if len(texto) < 3:
        return None, (jsonify(erro="Escreva uma pergunta.", campo="pergunta"), 400)
    if len(texto) > MAX_PERGUNTA:
        return None, (jsonify(erro=f"A pergunta pode ter até {MAX_PERGUNTA} caracteres.", campo="pergunta"), 400)
    if not gemini.ativo():
        return None, (jsonify(erro="Preencha GEMINI_API_KEY no .env para usar o laboratório."), 409)
    return texto, None


def _gemini_fora(erro):
    log.warning("Laboratório: %s", erro)
    return jsonify(erro="O Gemini não respondeu. Tente de novo em instantes.", detalhe=str(erro)[:300]), 503


@bp.get("/laboratorio")
@admin_obrigatorio
def laboratorio():
    return render_template("admin/laboratorio.html", pergunta=(request.args.get("q") or "")[:MAX_PERGUNTA],
                           limiar=busca.LIMIAR, top_k=busca.TOP_K, dimensoes=gemini.dimensoes(), ativo=gemini.ativo(),
                           modelo=gemini.modelo(), modelo_embedding=gemini.modelo_embedding(), maximo=MAX_PERGUNTA)


@bp.post("/laboratorio/perguntar")
@admin_obrigatorio
def lab_perguntar():
    pergunta, erro = _pergunta()
    if erro:
        return erro
    try:
        return jsonify(rag.responder(pergunta, tipo="laboratorio", detalhes=True))
    except gemini.ErroIA as e:
        return _gemini_fora(e)


@bp.post("/laboratorio/sem-rag")
@admin_obrigatorio
def lab_sem_rag():
    pergunta, erro = _pergunta()
    if erro:
        return erro
    try:
        return jsonify(rag.responder_sem_rag(pergunta))
    except gemini.ErroIA as e:
        return _gemini_fora(e)


def _item(p, similaridade=None):
    return {"nome": p["nome"], "url": f"/produto/{p['slug']}", "preco": brl(p["preco_final"]),
            "imagem": miniatura(p["imagens"][0]) if p["imagens"] else "/static/img/sem-foto.svg",
            "similaridade": similaridade}


@bp.post("/laboratorio/comparar")
@admin_obrigatorio
def lab_comparar():
    """A mesma frase na busca por texto (a do trabalho anterior) e na vetorial (a da página /busca de hoje)."""
    pergunta, erro = _pergunta()
    if erro:
        return erro
    try:
        ids, r = busca.ids_semelhantes(pergunta, 6)
    except gemini.ErroIA as e:
        return _gemini_fora(e)
    similar = {t["referencia"]: t["similaridade"] for t in r["trechos"]}
    por_texto, _ = mongo.listar(mongo.montar_filtro(q=pergunta), "relevancia", 6)
    return jsonify(texto=[_item(p) for p in por_texto],
                   vetorial=[_item(p, similar[p["id"]]) for p in mongo.por_ids(ids)], filtros=r["filtros"])


@bp.post("/laboratorio/plano")
@admin_obrigatorio
def lab_plano():
    """Com poucas linhas o Postgres prefere ler a tabela toda. O segundo plano desliga essa opção só dentro da
    transação (SET LOCAL), para mostrar o índice HNSW em uso."""
    pergunta, erro = _pergunta()
    if erro:
        return erro
    try:
        vetor, _, _ = busca.vetor_da_pergunta(pergunta)
    except gemini.ErroIA as e:
        return _gemini_fora(e)
    return jsonify(normal=vetorial.plano(vetor), indice=vetorial.plano(vetor, forcar_indice=True))


# ---------------------------------------------------------------- documentos da base

class _ArquivoInvalido(Exception):
    pass


def _uuid(valor):
    try:
        return str(UUID(str(valor)))
    except ValueError:
        return None


def _texto_do_arquivo(nome, conteudo):
    extensao = PurePath(nome).suffix.lower()
    if extensao not in EXTENSOES:
        raise _ArquivoInvalido("Envie um arquivo .md, .txt ou .pdf.")
    if not conteudo:
        raise _ArquivoInvalido("O arquivo está vazio.")
    if len(conteudo) > MAX_ARQUIVO:
        raise _ArquivoInvalido("O arquivo pode ter até 2 MB.")
    if extensao == ".pdf":
        if not conteudo.startswith(b"%PDF"):
            raise _ArquivoInvalido("Este arquivo não é um PDF de verdade.")
        try:
            texto = textos.texto_de_pdf(conteudo)
        except Exception as erro:  # PDF protegido por senha ou danificado
            log.warning("PDF %s não pôde ser lido: %r", nome, erro)
            raise _ArquivoInvalido("Não consegui ler este PDF. Confira se ele abre e não tem senha.") from erro
        if not texto:
            raise _ArquivoInvalido("Este PDF não tem texto (parece escaneado). Envie uma versão com texto.")
        return texto
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252", errors="replace")
    if "\x00" in texto:
        raise _ArquivoInvalido("Este arquivo não é um texto.")
    if not texto.strip():
        raise _ArquivoInvalido("O arquivo está vazio.")
    return texto


def _conferir_texto(titulo, texto):
    erros = {}
    if not 2 <= len(titulo) <= 120:
        erros["titulo"] = "Use de 2 a 120 caracteres."
    if len(texto.strip()) < 20:
        erros["texto"] = "Escreva pelo menos 20 caracteres."
    elif len(texto) > MAX_TEXTO:
        erros["texto"] = f"O texto tem {len(texto):,} caracteres; o limite é {MAX_TEXTO:,}.".replace(",", ".")
    return erros


def resumo_documento(d):
    """O que a lista mostra. 'fixo' = veio da pasta conhecimento/: o texto é editado no arquivo, não no painel."""
    return {"id": str(d["id"]), "titulo": d["titulo"], "origem": d["origem"], "fixo": d["origem"].startswith(PASTA),
            "caracteres": d["caracteres"], "trechos": d["trechos"], "ativo": d["ativo"],
            "indexado": bool(d["trechos"]), "atualizado_em": d["atualizado_em"].isoformat()}


def _indexar_documento(documento_id):
    """Devolve (resultado, aviso). O documento fica salvo mesmo se o Gemini falhar."""
    if not gemini.ativo():
        return None, "Documento salvo, mas sem GEMINI_API_KEY ele não entra no índice."
    try:
        return indexador.indexar_documentos("painel", documento_id), None
    except gemini.ErroIA as erro:
        log.warning("Documento %s salvo sem indexar: %s", documento_id, erro)
        return None, "Documento salvo, mas o Gemini não respondeu. Indexe de novo em instantes."


def _resposta_documento(documento_id, **extra):
    resultado, aviso = _indexar_documento(documento_id)
    return jsonify(documento=resumo_documento(vetorial.documento(documento_id)), indexacao=resultado, aviso=aviso,
                   **extra)


@bp.get("/documentos")
@admin_obrigatorio
def documentos():
    try:
        lista = [resumo_documento(d) for d in vetorial.listar_documentos()]
    except psycopg.Error as erro:
        if _sem_tabelas(erro):
            return render_template("admin/assistente.html", sem_tabelas=True)
        raise
    return render_template("admin/documentos.html", maximo=MAX_TEXTO, documentos=lista, ia_ativa=gemini.ativo())


@bp.post("/documentos")
@admin_obrigatorio
def enviar_documento():
    """Arquivo (multipart, campo 'arquivo') ou texto escrito no painel (JSON: titulo e texto)."""
    arquivo = request.files.get("arquivo")
    if arquivo and arquivo.filename:
        nome = re.sub(r"[^\w .()-]+", "", PurePath(arquivo.filename.replace("\\", "/")).name).strip()[:100]
        try:
            texto = _texto_do_arquivo(nome, arquivo.stream.read(MAX_ARQUIVO + 1))
        except _ArquivoInvalido as erro:
            return jsonify(erro=str(erro), campo="arquivo"), 400
        base = PurePath(nome).stem.replace("-", " ").replace("_", " ").strip() or "Documento"
        titulo = textos.titulo_markdown(texto, base[:1].upper() + base[1:])[:120]
        origem = f"upload: {nome}"
    elif request.is_json:
        dados = request.get_json(silent=True) or {}
        titulo, texto = " ".join(str(dados.get("titulo") or "").split()), str(dados.get("texto") or "")
        origem = f"painel: {titulo}"
    else:
        return jsonify(erro="Escolha um arquivo.", campo="arquivo"), 400
    erros = _conferir_texto(titulo, texto)
    if erros:
        return jsonify(erro=next(iter(erros.values())), campos=erros), 400
    substituiu = vetorial.documento_da_origem(origem) is not None
    documento_id = vetorial.salvar_documento(titulo, origem, texto.strip())
    return _resposta_documento(documento_id, substituiu=substituiu)


def _documento_ou_404(documento_id):
    doc = vetorial.documento(_uuid(documento_id)) if _uuid(documento_id) else None
    return doc, (None if doc else (jsonify(erro="Documento não encontrado."), 404))


@bp.get("/documentos/<documento_id>")
@admin_obrigatorio
def ver_documento(documento_id):
    """Texto completo e os trechos que vão para o banco vetorial, com a sobreposição separada."""
    doc, erro = _documento_ou_404(documento_id)
    if erro:
        return erro
    return jsonify(documento=resumo_documento(doc), texto=doc["texto"],
                   trechos=textos.marcar_sobreposicao(doc["titulo"], doc["texto"]))


@bp.post("/documentos/<documento_id>")
@admin_obrigatorio
def editar_documento(documento_id):
    doc, erro = _documento_ou_404(documento_id)
    if erro:
        return erro
    if doc["origem"].startswith(PASTA):
        return jsonify(erro=f"Este documento vem do arquivo {doc['origem']}. Edite o arquivo e rode "
                            "scripts/indexar.py --documentos."), 409
    dados = request.get_json(silent=True) or {}
    titulo, texto = " ".join(str(dados.get("titulo") or "").split()), str(dados.get("texto") or "")
    erros = _conferir_texto(titulo, texto)
    if erros:
        return jsonify(erro=next(iter(erros.values())), campos=erros), 400
    if dados.get("visto_em") and dados["visto_em"] != doc["atualizado_em"].isoformat():
        return jsonify(erro="Outra pessoa salvou este documento enquanto você editava. Recarregue para ver a versão "
                            "nova.", conflito=True), 409
    vetorial.editar_documento(doc["id"], titulo, texto.strip())
    return _resposta_documento(doc["id"])


@bp.post("/documentos/<documento_id>/indexar")
@admin_obrigatorio
def indexar_documento(documento_id):
    doc, erro = _documento_ou_404(documento_id)
    return erro or _resposta_documento(doc["id"])


@bp.post("/documentos/<documento_id>/ativo")
@admin_obrigatorio
def alternar_documento(documento_id):
    """Desativado, o documento continua salvo, mas os vetores dele saem do índice."""
    doc, erro = _documento_ou_404(documento_id)
    if erro:
        return erro
    if not vetorial.alternar_documento(doc["id"]):
        vetorial.remover_referencias(["documento"], [str(doc["id"])])
        vetorial.definir_trechos_documento(doc["id"], 0)
        return jsonify(documento=resumo_documento(vetorial.documento(doc["id"])), indexacao=None, aviso=None)
    return _resposta_documento(doc["id"])


@bp.post("/documentos/<documento_id>/excluir")
@admin_obrigatorio
def excluir_documento(documento_id):
    doc, erro = _documento_ou_404(documento_id)
    if erro:
        return erro
    if doc["origem"].startswith(PASTA):
        return jsonify(erro="Este documento vem de um arquivo do projeto: ele voltaria na próxima indexação. "
                            "Desative em vez de excluir."), 409
    vetorial.excluir_documento(doc["id"])
    return jsonify(ok=True)


# ---------------------------------------------------------------- perguntas dos clientes

@bp.get("/perguntas")
@admin_obrigatorio
def perguntas():
    filtro = request.args.get("filtro") if request.args.get("filtro") in FILTROS_PERGUNTAS else "todas"
    tipo = request.args.get("tipo") if request.args.get("tipo") in ("chat", "busca") else None
    pagina = max(1, request.args.get("pagina", 1, type=int))
    try:
        itens = vetorial.listar_interacoes(filtro, tipo, POR_PAGINA + 1, (pagina - 1) * POR_PAGINA)
    except psycopg.Error as erro:
        if _sem_tabelas(erro):
            return render_template("admin/assistente.html", sem_tabelas=True)
        raise
    return render_template("admin/perguntas.html", itens=itens[:POR_PAGINA], tem_mais=len(itens) > POR_PAGINA,
                           pagina=pagina, filtro=filtro, tipo=tipo, filtros=FILTROS_PERGUNTAS, limiar=busca.LIMIAR)
