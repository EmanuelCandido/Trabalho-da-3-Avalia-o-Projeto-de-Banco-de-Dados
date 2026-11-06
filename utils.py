"""Funções compartilhadas: visitante, CSRF, moeda, carrinho e mensagem do WhatsApp."""
import secrets
from time import perf_counter
import uuid
from functools import wraps
from urllib.parse import quote

from flask import abort, current_app, jsonify, redirect, request, session, url_for

from bancos import mongo, redis_store, supabase

PADROES_LOJA = {
    "loja_nome": "NOMA",
    "whatsapp_numero": None,  # cai no WHATSAPP_NUMERO do .env
    "faixa_promocional": "10% OFF EXTRA NO PIX",
    "faixa_termina_em": "",
}


# ---------------------------------------------------------------- sessão

def visitante():
    """Identificador anônimo do visitante: chave do carrinho e dos vistos no Redis."""
    if "vid" not in session:
        session["vid"] = uuid.uuid4().hex
        session.permanent = True
    return session["vid"]


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def conferir_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        enviado = request.headers.get("X-CSRF-Token") or request.form.get("csrf")
        if not enviado or not secrets.compare_digest(enviado, session.get("csrf", "")):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify(erro="Sua sessão expirou. Recarregue a página."), 400
            abort(400)
    return None


def admin_obrigatorio(view):
    @wraps(view)
    def interna(*args, **kwargs):
        if not session.get("admin"):
            if request.is_json or request.headers.get("X-Requested-With") == "fetch":
                return jsonify(erro="Faça login novamente."), 401
            return redirect(url_for("admin.login", proximo=request.path))
        return view(*args, **kwargs)
    return interna


def ip_cliente():
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "?").split(",")[0].strip()


# ---------------------------------------------------------------- formatação

def brl(valor):
    try:
        valor = float(valor or 0)
    except (TypeError, ValueError):
        valor = 0.0
    inteiro, centavos = f"{valor:,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


def parcelas(valor, vezes=3):
    return f"ou {vezes}x de {brl(float(valor) / vezes)} sem juros"


def ler_preco(texto):
    """Aceita '1.299,90', '1299,90' e '1299.90'."""
    if texto is None:
        return None
    texto = str(texto).strip().replace("R$", "").replace(" ", "")
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return round(float(texto), 2)


# ---------------------------------------------------------------- imagens responsivas

PASTA_PRODUTOS = "/static/img/produtos/"


def miniatura(url):
    """Versão de 480 px das fotos do catálogo (cards, carrinho e listas); outras URLs ficam iguais."""
    if url and url.startswith(PASTA_PRODUTOS) and url.endswith(".webp") and not url.endswith("-480.webp"):
        return url[:-5] + "-480.webp"
    return url


def srcset(url):
    """srcset com os dois tamanhos (480 e 900 px) para o navegador escolher pelo tamanho da tela."""
    mini = miniatura(url)
    return f"{mini} 480w, {url} 900w" if mini != url else ""


# ---------------------------------------------------------------- configurações da loja

_config_memoria = {"dados": None, "lida_em": 0.0, "versao": None}


def config_loja():
    """Configurações vindas do Supabase, com cache no Redis e uma cópia de 30 s na memória do servidor
    (assim a maioria das páginas não gasta nenhuma ida à rede só para isso)."""
    agora = perf_counter()
    versao = redis_store._versao_local["valor"]
    if (_config_memoria["dados"] is not None and agora - _config_memoria["lida_em"] < 30
            and _config_memoria["versao"] == versao):
        return _config_memoria["dados"]
    final = _config_loja_banco()
    _config_memoria.update(dados=final, lida_em=agora, versao=redis_store._versao_local["valor"])
    return final


def _config_loja_banco():
    def carregar():
        try:
            return supabase.configuracoes() if supabase.configurado() else {}
        except Exception:
            return {}
    try:
        dados = redis_store.lembrar("config", carregar, ttl=60)
    except Exception:
        dados = carregar()
    final = {**PADROES_LOJA, **{k: v for k, v in (dados or {}).items() if v}}
    final["whatsapp_numero"] = "".join(c for c in (final.get("whatsapp_numero") or
                                                   current_app.config["WHATSAPP_NUMERO"]) if c.isdigit())
    return final


# ---------------------------------------------------------------- carrinho

def montar_carrinho(vid):
    """Junta o hash do Redis com os dados atuais dos produtos no MongoDB."""
    bruto = redis_store.carrinho(vid)
    if not bruto:
        return {"itens": [], "total": 0, "qtd": 0, "economia": 0, "total_fmt": brl(0)}
    partes = {chave: chave.split("|") for chave in bruto}
    produtos = {p["id"]: p for p in mongo.por_ids(list({p[0] for p in partes.values()}))}
    itens, total, qtd, economia = [], 0.0, 0, 0.0
    for chave, quantidade in bruto.items():
        produto_id, cor, tamanho = (partes[chave] + ["", ""])[:3]
        p = produtos.get(produto_id)
        if not p:
            redis_store.definir_quantidade(vid, chave, 0)  # produto removido ou desativado
            continue
        subtotal = round(p["preco_final"] * quantidade, 2)
        total += subtotal
        qtd += quantidade
        economia += (p["preco"] - p["preco_final"]) * quantidade
        imagem = miniatura(p["imagens"][0]) if p["imagens"] else url_for("static", filename="img/sem-foto.svg")
        itens.append({
            "chave": chave, "produto_id": produto_id, "slug": p["slug"], "nome": p["nome"],
            "cor": cor, "tamanho": tamanho, "quantidade": quantidade, "estoque": p["estoque"],
            "sem_estoque": quantidade > p["estoque"],
            "preco_unitario": p["preco_final"], "preco_original": p["preco"],
            "preco_fmt": brl(p["preco_final"]), "preco_original_fmt": brl(p["preco"]) if p["preco"] > p["preco_final"] else "",
            "subtotal": subtotal, "subtotal_fmt": brl(subtotal), "imagem": imagem,
            "url": url_for("loja.produto", slug=p["slug"]),
        })
    itens.sort(key=lambda i: i["nome"])
    return {"itens": itens, "total": round(total, 2), "qtd": qtd, "economia": round(economia, 2),
            "total_fmt": brl(total), "economia_fmt": brl(economia)}


def descrever_item(item):
    detalhes = ", ".join(x for x in (item.get("cor"), item.get("tamanho")) if x and x != "Único")
    return f"{item['quantidade']}x {item['nome']}" + (f" ({detalhes})" if detalhes else "")


def mensagem_whatsapp(itens, total, codigo=None, nome=None, observacao=None):
    """Formato pedido no enunciado: 'Olá, gostaria de pedir: 1x Produto A, 2x Produto B. Total: R$ XX'."""
    texto = f"Olá, gostaria de pedir: {', '.join(descrever_item(i) for i in itens)}. Total: {brl(total)}"
    extras = []
    if codigo:
        extras.append(f"Pedido: {codigo}")
    if nome:
        extras.append(f"Nome: {nome}")
    if observacao:
        extras.append(f"Observação: {observacao}")
    if extras:
        texto += "\n\n" + "\n".join(extras)
    return texto


def link_whatsapp(numero, texto):
    return f"https://wa.me/{numero}?text={quote(texto)}"
