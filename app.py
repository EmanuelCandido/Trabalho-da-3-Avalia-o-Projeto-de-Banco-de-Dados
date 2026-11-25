"""NOMA — e-commerce com banco de dados poliglota (MongoDB + Supabase + Redis).

Rodar: python app.py  →  http://127.0.0.1:5000
"""
import os
from datetime import datetime, timedelta

from flask import Flask, jsonify, render_template, request, session, url_for
from flask_compress import Compress
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

import admin
import admin_ia
import assistente
import loja
from bancos import mongo, redis_store, supabase
from config import Config
from ia import busca as ia_busca
from ia import gemini, indexador, rag
from utils import (banner_srcset, brl, config_loja, conferir_csrf, csrf_token, miniatura, parcelas,
                   srcset)


def criar_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = timedelta(days=30)
    # Rede lenta: HTML, CSS, JS e JSON comprimidos (brotli ou gzip) e estáticos guardados no navegador.
    app.config.update(COMPRESS_ALGORITHM=["br", "gzip"], COMPRESS_MIN_SIZE=600, COMPRESS_LEVEL=6, COMPRESS_BR_LEVEL=5,
                      SEND_FILE_MAX_AGE_DEFAULT=timedelta(days=30))
    Compress(app)

    mongo.init(app.config["MONGO_URI"], app.config["MONGO_DB"])
    redis_store.init(app.config["REDIS_URL"], app.config["CACHE_TTL"])
    supabase.init(app.config["DATABASE_URL"], app.config["SUPABASE_URL"],
                  app.config["SUPABASE_ANON_KEY"], app.config["SUPABASE_SERVICE_ROLE_KEY"])
    # IA: sem GEMINI_API_KEY tudo continua funcionando, só sem o assistente e sem a busca por significado.
    gemini.init(app.config["GEMINI_API_KEY"], app.config["GEMINI_MODELO"], app.config["GEMINI_MODELO_EMBEDDING"],
                app.config["EMBEDDING_DIM"], reserva=app.config["GEMINI_MODELO_RESERVA"])
    ia_busca.init(app.config["RAG_LIMIAR"], app.config["RAG_TOP_K"])
    rag.init(app.config["IA_LIMITE_DIA"])
    indexador.init(app.config["N8N_WEBHOOK_URL"], app.config["N8N_SEGREDO"])

    app.register_blueprint(loja.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(admin_ia.bp)
    app.register_blueprint(assistente.bp)
    app.before_request(conferir_csrf)

    app.jinja_env.filters["brl"] = brl
    app.jinja_env.filters["parcelas"] = parcelas
    app.jinja_env.globals.update(miniatura=miniatura, srcset=srcset, banner_srcset=banner_srcset)

    @app.template_filter("data")
    def data(valor, formato="%d/%m/%Y %H:%M"):
        if isinstance(valor, str):
            try:
                valor = datetime.fromisoformat(valor)
            except ValueError:
                return valor
        if not valor:
            return ""
        if valor.tzinfo:
            valor = valor.astimezone()
        return valor.strftime(formato)

    def url_atual(**mudar):
        """URL da página atual trocando alguns parâmetros (None remove). Usada pelos filtros."""
        args = request.args.to_dict()
        args.pop("pagina", None)
        args.pop("parcial", None)
        for chave, valor in mudar.items():
            if valor is None or args.get(chave) == valor and chave != "ordem":
                args.pop(chave, None)  # clicar de novo no filtro ativo desmarca
            else:
                args[chave] = valor
        return url_for(request.endpoint, **(request.view_args or {}), **args)

    @app.context_processor
    def globais():
        qtd = 0
        if not request.path.startswith(("/admin", "/static", "/imagem")):
            # Visitante novo ainda não tem carrinho: não gasta uma ida ao Redis.
            if session.get("vid"):
                try:
                    qtd = sum(redis_store.carrinho(session["vid"]).values())
                except RedisError:
                    qtd = 0
        return {"csrf_token": csrf_token, "qtd_carrinho": qtd, "url_atual": url_atual,
                "loja": config_loja() if not request.path.startswith("/static") else {},
                "ano": datetime.now().year, "versao_estatico": "26", "ia_ativa": gemini.ativo()}

    @app.after_request
    def cabecalhos(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resposta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if request.path.startswith("/static/") and request.args.get("v"):
            # CSS e JS levam ?v=N no endereço: podem ficar no cache por 1 ano sem risco de versão velha.
            resposta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resposta

    @app.get("/favicon.ico")
    def favicon():
        # navegadores pedem /favicon.ico mesmo com o ícone SVG declarado na página
        return app.send_static_file("img/favicon.svg")

    @app.get("/robots.txt")
    def robots():
        """Buscadores e robôs ficam fora da busca, dos filtros e das APIs: cada combinação de filtros é uma página
        nova para eles, e cada página gasta comandos do Redis (o plano gratuito tem 500 mil por mês)."""
        texto = ("User-agent: *\nDisallow: /admin\nDisallow: /api/\nDisallow: /busca\nDisallow: /*?*\n"
                 "Allow: /\n")
        return app.response_class(texto, mimetype="text/plain", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/api/saude")
    def saude():
        """Chamada todo dia pelo cron da Vercel (vercel.json). Uma consulta simples ao Postgres conta como uso:
        sem ela, o Supabase gratuito pausa o projeto depois de uma semana parado (o professor pode testar depois)."""
        inicio = datetime.now()
        try:
            supabase.ping()
        except Exception:
            app.logger.exception("Saúde: o Postgres não respondeu")
            return jsonify(ok=False), 503
        resposta = jsonify(ok=True, postgres_ms=round((datetime.now() - inicio).total_seconds() * 1000))
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.errorhandler(404)
    def nao_encontrado(_erro):
        if request.path.startswith("/api/"):
            return jsonify(erro="Não encontrado."), 404
        return render_template("loja/erro.html", codigo=404, titulo="Página não encontrada",
                               texto="O endereço pode ter mudado ou o produto saiu da loja."), 404

    @app.errorhandler(PyMongoError)
    @app.errorhandler(RedisError)
    def banco_fora(erro):
        app.logger.exception("Falha de banco: %s", erro)
        if request.path.startswith("/api/") or request.headers.get("X-Requested-With") == "fetch":
            return jsonify(erro="Um dos bancos não respondeu. Tente de novo."), 503
        return render_template("loja/erro.html", codigo=503, titulo="Estamos com uma instabilidade",
                               texto="Um dos bancos de dados não respondeu. Tente de novo em instantes."), 503

    return app


app = criar_app()

if __name__ == "__main__":
    porta = int(os.getenv("PORT", "5000"))
    if os.getenv("FLASK_DEBUG") == "1":
        app.run(host="127.0.0.1", port=porta, debug=True)
    else:
        from waitress import serve
        print(f"NOMA rodando em http://127.0.0.1:{porta}")
        serve(app, host="127.0.0.1", port=porta, threads=8)
