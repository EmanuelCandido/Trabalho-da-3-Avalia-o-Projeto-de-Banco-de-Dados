"""NOMA — e-commerce com banco de dados poliglota (MongoDB + Supabase + Redis).

Rodar: python app.py  →  http://127.0.0.1:5000
"""
import os
from datetime import datetime, timedelta

from flask import Flask, jsonify, render_template, request, url_for
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

import admin
import loja
from bancos import mongo, redis_store, supabase
from config import Config
from utils import brl, config_loja, conferir_csrf, csrf_token, parcelas, visitante


def criar_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = timedelta(days=30)

    mongo.init(app.config["MONGO_URI"], app.config["MONGO_DB"])
    redis_store.init(app.config["REDIS_URL"], app.config["CACHE_TTL"])
    supabase.init(app.config["DATABASE_URL"], app.config["SUPABASE_URL"],
                  app.config["SUPABASE_ANON_KEY"], app.config["SUPABASE_SERVICE_ROLE_KEY"])

    app.register_blueprint(loja.bp)
    app.register_blueprint(admin.bp)
    app.before_request(conferir_csrf)

    app.jinja_env.filters["brl"] = brl
    app.jinja_env.filters["parcelas"] = parcelas

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
            try:
                qtd = sum(redis_store.carrinho(visitante()).values())
            except RedisError:
                qtd = 0
        return {"csrf_token": csrf_token, "qtd_carrinho": qtd, "url_atual": url_atual,
                "loja": config_loja() if not request.path.startswith("/static") else {},
                "ano": datetime.now().year, "versao_estatico": "10"}

    @app.after_request
    def cabecalhos(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resposta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
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
