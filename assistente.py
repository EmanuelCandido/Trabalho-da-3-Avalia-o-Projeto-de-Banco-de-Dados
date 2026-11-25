"""API do assistente (RAG) e rotas internas usadas pelo n8n.

Públicas (loja):
    POST /api/assistente              {pergunta, produto_id?} -> resposta, cards, fontes e tempos
    GET  /api/assistente/historico    conversa guardada no Redis (2 h)
    POST /api/assistente/avaliar      {id, nota: 1 | -1}
    POST /api/assistente/limpar

Internas (n8n), exigem o cabeçalho X-NOMA-Segredo igual ao N8N_SEGREDO do .env:
    GET  /api/interno/produto/<id>/documentos   textos prontos para virar vetor (mesmos do Python)
    GET  /api/interno/produtos                  produtos ativos (reindexação noturna)
"""
import logging
import secrets

import psycopg
from flask import Blueprint, abort, current_app, jsonify, request, session
from redis.exceptions import RedisError

from bancos import mongo, redis_store, vetorial
from ia import gemini, indexador, rag
from utils import config_loja, link_whatsapp, visitante

bp = Blueprint("assistente", __name__)
log = logging.getLogger("noma.ia")

MAX_PERGUNTA = 500
LIMITE_POR_VISITANTE = 15     # perguntas a cada 10 minutos


@bp.post("/api/assistente")
def perguntar():
    if not gemini.ativo():
        return jsonify(erro="O assistente está desligado no momento."), 503
    dados = request.get_json(silent=True) or {}
    pergunta = " ".join(str(dados.get("pergunta") or "").split())
    if len(pergunta) < 3:
        return jsonify(erro="Escreva a sua pergunta.", campo="pergunta"), 400
    if len(pergunta) > MAX_PERGUNTA:
        return jsonify(erro=f"A pergunta pode ter até {MAX_PERGUNTA} caracteres.", campo="pergunta"), 400

    vid = visitante()
    try:
        pode, espera = redis_store.contar_pergunta(vid, LIMITE_POR_VISITANTE)
    except RedisError:
        pode, espera = True, 0
    if not pode:
        minutos = max(1, round(espera / 60))
        return jsonify(erro=f"Você fez muitas perguntas seguidas. Tente de novo em {minutos} min."), 429

    produto_id = str(dados.get("produto_id") or "")[:40] or None
    try:
        r = rag.responder(pergunta, visitante=vid, produto_id=produto_id)
    except gemini.ErroIA as erro:
        log.warning("Embedding da pergunta falhou: %s", erro)
        return jsonify(erro="Não consegui consultar a base agora. Tente de novo em instantes."), 503
    except psycopg.Error:
        current_app.logger.exception("Falha no banco vetorial")
        return jsonify(erro="O banco de conhecimento não respondeu. Tente de novo em instantes."), 503

    if r["sem_resposta"]:
        r["whatsapp"] = link_whatsapp(config_loja()["whatsapp_numero"],
                                      f"Olá! Perguntei ao assistente da NOMA e não encontrei a resposta: {pergunta}")
    return jsonify(r)


@bp.get("/api/assistente/historico")
def historico():
    mensagens = []
    if session.get("vid"):  # visitante novo ainda não conversou: nem consulta o Redis
        try:
            mensagens = redis_store.historico_chat(session["vid"])
        except RedisError:
            mensagens = []
    return jsonify(ativo=gemini.ativo(), mensagens=mensagens)


@bp.post("/api/assistente/avaliar")
def avaliar():
    dados = request.get_json(silent=True) or {}
    try:
        interacao_id, nota = int(dados.get("id")), int(dados.get("nota"))
    except (TypeError, ValueError):
        return jsonify(erro="Avaliação inválida."), 400
    if nota not in (1, -1):
        return jsonify(erro="Avaliação inválida."), 400
    ok = vetorial.avaliar_interacao(interacao_id, rag.visitante_hash(visitante()), nota)
    return jsonify(ok=ok), (200 if ok else 404)


@bp.post("/api/assistente/limpar")
def limpar():
    try:
        redis_store.limpar_chat(visitante())
    except RedisError:
        pass
    return jsonify(ok=True)


# ---------------------------------------------------------------- rotas internas (n8n)

def _exigir_segredo():
    """Sem N8N_SEGREDO no .env as rotas internas nem existem (404)."""
    esperado = current_app.config.get("N8N_SEGREDO") or ""
    enviado = request.headers.get("X-NOMA-Segredo") or ""
    if not esperado or not secrets.compare_digest(enviado, esperado):
        abort(404)


@bp.get("/api/interno/produto/<produto_id>/documentos")
def interno_documentos(produto_id):
    """O n8n busca aqui os textos de um produto. Lista vazia = produto inativo ou excluído (o n8n apaga os vetores)."""
    _exigir_segredo()
    p = mongo.por_id(produto_id, completo=True)
    return jsonify(produto_id=produto_id, modelo=gemini.modelo_embedding(), dimensoes=gemini.dimensoes(),
                   fontes=list(indexador.FONTES_PRODUTO), trechos=indexador.trechos_do_produto(p))


@bp.get("/api/interno/produtos")
def interno_produtos():
    _exigir_segredo()
    return jsonify(produtos=[{"id": p["id"], "nome": p["nome"]} for p in indexador.produtos_ativos()])
