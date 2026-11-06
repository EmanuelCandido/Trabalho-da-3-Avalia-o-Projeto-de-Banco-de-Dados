"""Módulo do cliente (público): catálogo, produto, carrinho e finalização pelo WhatsApp."""
import json

from flask import Blueprint, Response, abort, jsonify, render_template, request

from bancos import mongo, redis_store, supabase
from utils import (brl, config_loja, link_whatsapp, mensagem_whatsapp, montar_carrinho, visitante)

bp = Blueprint("loja", __name__)

POR_PAGINA = 12
LISTAGENS = {
    "roupas": {"titulo": "Roupas", "subtitulo": "Peças essenciais para combinar com a vida que acontece.",
               "rotulo": "Todas as roupas", "filtro": {"categoria": "Roupas"}},
    "acessorios": {"titulo": "Acessórios", "subtitulo": "Os detalhes que completam o seu jeito.",
                   "rotulo": "Todos os acessórios", "filtro": {"categoria": "Acessórios"}},
    "novidades": {"titulo": "Novidades", "subtitulo": "Acabou de chegar na NOMA.",
                  "rotulo": "Todas as novidades", "filtro": {"destaque": "novidade"}},
    "ofertas": {"titulo": "Ofertas da Black", "subtitulo": "Até 30% OFF na coleção primavera.",
                "rotulo": "Todas as ofertas", "filtro": {"destaque": "oferta"}},
}
FILTROS = ("genero", "tamanho", "cor", "preco", "material")


def _vistos(ignorar=None):
    try:
        return mongo.por_ids(redis_store.vistos(visitante(), ignorar=ignorar, limite=8))
    except Exception:
        return []


# ---------------------------------------------------------------- páginas

@bp.get("/")
def inicio():
    def vitrine():
        ofertas, _ = mongo.listar(mongo.montar_filtro(destaque="oferta"), "relevancia", 8)
        acessorios, _ = mongo.listar(mongo.montar_filtro(categoria="Acessórios"), "relevancia", 3)
        queridinhos, _ = mongo.listar(mongo.montar_filtro(destaque="queridinho"), "mais-vendidos", 3)
        return {"ofertas": ofertas, "acessorios": acessorios, "queridinhos": queridinhos}
    dados = redis_store.lembrar("vitrine:inicio", vitrine)
    return render_template("loja/inicio.html", **dados, vistos=_vistos())


@bp.get("/<any(roupas, acessorios, novidades, ofertas):secao>")
def listagem(secao):
    return _listagem(secao)


@bp.get("/busca")
def busca():
    return _listagem("busca")


def _listagem(secao):
    q = (request.args.get("q") or "").strip()[:80]
    if secao == "busca":
        info = {"titulo": f"Busca: “{q}”" if q else "Busca", "subtitulo": "Resultados na loja toda.",
                "rotulo": "Resultados", "filtro": {}}
    else:
        info = LISTAGENS[secao]
    escolhidos = {f: request.args.get(f) for f in FILTROS if request.args.get(f)}
    ordem = request.args.get("ordem", "relevancia")
    pagina = max(1, request.args.get("pagina", 1, type=int))
    filtro_mongo = mongo.montar_filtro(**info["filtro"], **escolhidos, q=q or None)

    chave = "lista:" + json.dumps({"s": secao, "q": q, "f": escolhidos, "o": ordem, "p": pagina}, sort_keys=True)
    itens, total = redis_store.lembrar(chave, lambda: mongo.listar(
        filtro_mongo, ordem, POR_PAGINA, (pagina - 1) * POR_PAGINA))
    tem_mais = pagina * POR_PAGINA < total

    if request.args.get("parcial"):
        return jsonify(html=render_template("loja/_grade.html", produtos=itens, inicio=(pagina - 1) * POR_PAGINA),
                       total=total, tem_mais=tem_mais, pagina=pagina)

    categoria = info["filtro"].get("categoria")
    opcoes = redis_store.lembrar(f"opcoes:{categoria or 'todas'}", lambda: mongo.opcoes_filtro(categoria))
    return render_template("loja/listagem.html", secao=secao, info=info, produtos=itens, total=total,
                           opcoes=opcoes, escolhidos=escolhidos, ordem=ordem, q=q, pagina=pagina,
                           tem_mais=tem_mais, ordens=ORDENS_ROTULOS, faixas=FAIXAS_ROTULOS)


ORDENS_ROTULOS = {"relevancia": "Relevância", "mais-vendidos": "Mais vendidos", "menor-preco": "Menor preço",
                  "maior-preco": "Maior preço", "novidades": "Novidades"}
FAIXAS_ROTULOS = {"ate-150": "Até R$ 150", "150-300": "R$ 150 a R$ 300", "300-500": "R$ 300 a R$ 500",
                  "acima-500": "Acima de R$ 500"}


@bp.get("/produto/<slug>")
def produto(slug):
    p = redis_store.lembrar(f"produto:{slug}", lambda: mongo.por_slug(slug))
    if not p:
        abort(404)
    try:
        redis_store.registrar_visto(visitante(), p["id"])
    except Exception:
        pass
    return render_template("loja/produto.html", p=p, vistos=_vistos(ignorar=p["id"]))


@bp.get("/sobre")
def sobre():
    return render_template("loja/sobre.html")


@bp.get("/atendimento")
def atendimento():
    return render_template("loja/atendimento.html")


@bp.get("/guia-de-tamanhos")
def guia():
    return render_template("loja/guia.html")


@bp.get("/imagem/<imagem_id>")
def imagem(imagem_id):
    """Imagens enviadas pelo admin, servidas direto do GridFS do MongoDB."""
    arquivo = mongo.ler_imagem(imagem_id)
    if not arquivo:
        abort(404)
    resposta = Response(arquivo.read(), mimetype=arquivo.content_type or "image/jpeg")
    resposta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resposta


# ---------------------------------------------------------------- API do carrinho (JSON)

@bp.get("/api/carrinho")
def api_carrinho():
    return jsonify(montar_carrinho(visitante()))


@bp.post("/api/carrinho")
def api_adicionar():
    dados = request.get_json(silent=True) or {}
    p = mongo.por_id(dados.get("produto_id"), completo=False)
    if not p or not p["ativo"]:
        return jsonify(erro="Produto não encontrado."), 404
    if p["estoque"] <= 0:
        return jsonify(erro="Este produto está esgotado."), 409
    cor = (dados.get("cor") or "").strip()
    tamanho = (dados.get("tamanho") or "").strip()
    nomes_cores = [c["nome"] for c in p["cores"]]
    if nomes_cores and cor not in nomes_cores:
        cor = nomes_cores[0] if len(nomes_cores) == 1 else ""
        if not cor:
            return jsonify(erro="Escolha uma cor.", campo="cor"), 400
    tamanhos = [t for t in p["tamanhos"] if t != "Único"]
    if tamanhos and tamanho not in tamanhos:
        return jsonify(erro="Escolha um tamanho.", campo="tamanho"), 400
    quantidade = max(1, min(int(dados.get("quantidade") or 1), 20))
    vid = visitante()
    chave = redis_store.chave_item(p["id"], cor, tamanho or ("Único" if "Único" in p["tamanhos"] else ""))
    atual = redis_store.carrinho(vid).get(chave, 0)
    if atual + quantidade > p["estoque"]:
        return jsonify(erro=f"Só temos {p['estoque']} unidade(s) em estoque."), 409
    redis_store.adicionar_item(vid, chave, quantidade)
    return jsonify(montar_carrinho(vid))


@bp.patch("/api/carrinho")
def api_quantidade():
    dados = request.get_json(silent=True) or {}
    vid = visitante()
    chave = dados.get("chave", "")
    if chave not in redis_store.carrinho(vid):
        return jsonify(erro="Item não está no carrinho."), 404
    quantidade = max(0, min(int(dados.get("quantidade") or 0), 20))
    p = mongo.por_id(chave.split("|")[0], completo=False)
    if p and quantidade > p["estoque"]:
        return jsonify(erro=f"Só temos {p['estoque']} unidade(s) em estoque.", **montar_carrinho(vid)), 409
    redis_store.definir_quantidade(vid, chave, quantidade)
    return jsonify(montar_carrinho(vid))


@bp.delete("/api/carrinho")
def api_remover():
    dados = request.get_json(silent=True) or {}
    vid = visitante()
    redis_store.definir_quantidade(vid, dados.get("chave", ""), 0)
    return jsonify(montar_carrinho(vid))


@bp.post("/api/pedido")
def api_pedido():
    """Grava o pedido no Supabase e devolve o link do WhatsApp com a mensagem formatada."""
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()[:80]
    observacao = (dados.get("observacao") or "").strip()[:300]
    vid = visitante()
    carrinho = montar_carrinho(vid)
    if not carrinho["itens"]:
        return jsonify(erro="Seu carrinho está vazio."), 400
    esgotados = [i["nome"] for i in carrinho["itens"] if i["sem_estoque"]]
    if esgotados:
        return jsonify(erro=f"Estoque insuficiente: {', '.join(esgotados)}."), 409

    itens_sql = [{"produto_id": i["produto_id"], "nome": i["nome"], "cor": i["cor"], "tamanho": i["tamanho"],
                  "quantidade": i["quantidade"], "preco_unitario": i["preco_unitario"]} for i in carrinho["itens"]]
    try:
        pedido = supabase.registrar_pedido(nome, observacao, itens_sql)
    except Exception:
        return jsonify(erro="Não conseguimos registrar o pedido agora. Tente de novo em instantes."), 503

    texto = mensagem_whatsapp(carrinho["itens"], pedido["total"], pedido["codigo"], nome, observacao)
    try:
        supabase.salvar_mensagem(pedido["id"], texto)
    except Exception:
        pass
    mongo.registrar_venda(itens_sql)
    redis_store.invalidar_cache()
    redis_store.esvaziar_carrinho(vid)
    numero = config_loja()["whatsapp_numero"]
    return jsonify(codigo=pedido["codigo"], total=brl(pedido["total"]), mensagem=texto,
                   url=link_whatsapp(numero, texto))


@bp.post("/api/mensagem")
def api_previa():
    """Prévia da mensagem (mostrada na janela de finalização antes de enviar)."""
    dados = request.get_json(silent=True) or {}
    carrinho = montar_carrinho(visitante())
    texto = mensagem_whatsapp(carrinho["itens"], carrinho["total"], None,
                              (dados.get("nome") or "").strip()[:80], (dados.get("observacao") or "").strip()[:300])
    return jsonify(mensagem=texto)


# ---------------------------------------------------------------- busca e avaliações

@bp.get("/api/busca")
def api_busca():
    q = (request.args.get("q") or "").strip()[:80]
    itens = redis_store.lembrar(f"sugestoes:{q.lower()}", lambda: mongo.sugestoes(q)) if len(q) >= 2 else []
    return jsonify(itens=[{"nome": i["nome"], "slug": i["slug"], "preco": brl(i["preco_final"]),
                           "imagem": i["imagens"][0] if i["imagens"] else "", "categoria": i["categoria"]}
                          for i in itens])


@bp.post("/api/produto/<slug>/avaliacao")
def api_avaliar(slug):
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()[:40]
    titulo = (dados.get("titulo") or "").strip()[:80]
    texto = (dados.get("texto") or "").strip()[:600]
    try:
        nota = int(dados.get("nota"))
    except (TypeError, ValueError):
        nota = 0
    erros = {}
    if not 1 <= nota <= 5:
        erros["nota"] = "Escolha de 1 a 5 estrelas."
    if len(nome) < 2:
        erros["nome"] = "Informe seu nome."
    if len(titulo) < 3:
        erros["titulo"] = "Dê um título à avaliação."
    if erros:
        return jsonify(erro="Confira os campos.", campos=erros), 400
    ok = mongo.adicionar_avaliacao(slug, {"nome": nome, "nota": nota, "titulo": titulo, "texto": texto,
                                          "tamanho": (dados.get("tamanho") or "")[:10],
                                          "cor": (dados.get("cor") or "")[:30]})
    if not ok:
        return jsonify(erro="Produto não encontrado."), 404
    redis_store.invalidar_cache()
    return jsonify(ok=True)


@bp.post("/api/vistos/limpar")
def api_limpar_vistos():
    redis_store.limpar_vistos(visitante())
    return jsonify(ok=True)
