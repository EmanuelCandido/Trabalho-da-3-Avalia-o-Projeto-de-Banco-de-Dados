"""Módulo administrativo (restrito): login pelo Supabase, cadastro de produtos no MongoDB e painel."""
import io
import json
import re
import secrets
from time import perf_counter

from flask import (Blueprint, flash, jsonify, redirect, render_template, request, session, url_for)
from PIL import Image, UnidentifiedImageError

from bancos import mongo, redis_store, supabase
from utils import admin_obrigatorio, config_loja, ip_cliente, ler_preco

bp = Blueprint("admin", __name__, url_prefix="/admin")

STATUS_PEDIDO = {"enviado_whatsapp": "Enviado ao WhatsApp", "confirmado": "Confirmado",
                 "entregue": "Entregue", "cancelado": "Cancelado"}


# ---------------------------------------------------------------- login

@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin"):
        return redirect(url_for("admin.dashboard"))
    erro, email, restantes = None, "", None
    ip = ip_cliente()
    try:
        bloqueio = redis_store.login_bloqueado(ip)
    except Exception:
        bloqueio = 0

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if bloqueio:
            erro = f"Muitas tentativas. Tente de novo em {max(1, bloqueio // 60)} min."
        else:
            try:
                admin = supabase.autenticar(email, request.form.get("senha") or "")
            except supabase.ErroLogin as e:
                erro = str(e)
                supabase.registrar_acesso(email, False, erro, ip)
                try:
                    restantes = redis_store.registrar_falha_login(ip)
                except Exception:
                    restantes = None
            except Exception:
                erro = "O banco de autenticação não respondeu. Confira a configuração do Supabase."
            else:
                supabase.registrar_acesso(email, True, admin["via"], ip)
                try:
                    redis_store.limpar_falhas_login(ip)
                except Exception:
                    pass
                vid = session.get("vid")
                session.clear()  # nova sessão a cada login (evita fixação de sessão)
                session.update(vid=vid, admin=admin, csrf=secrets.token_urlsafe(24))
                session.permanent = True
                proximo = request.args.get("proximo") or ""
                if not proximo.startswith("/admin") or proximo.startswith("//"):
                    proximo = url_for("admin.dashboard")
                flash(f"Bem-vindo(a), {admin['nome'].split()[0]}!", "ok")
                return redirect(proximo)
    return render_template("admin/login.html", erro=erro, email=email, restantes=restantes,
                           bloqueio=bloqueio, modo=supabase.modo_auth()), (401 if erro else 200)


@bp.post("/sair")
def sair():
    vid = session.get("vid")
    session.clear()
    if vid:
        session["vid"] = vid
    flash("Você saiu do painel.", "ok")
    return redirect(url_for("admin.login"))


# ---------------------------------------------------------------- dashboard

def _medir(func):
    inicio = perf_counter()
    try:
        func()
        return {"ok": True, "ms": round((perf_counter() - inicio) * 1000)}
    except Exception as erro:
        return {"ok": False, "ms": None, "erro": type(erro).__name__}


@bp.get("/")
@admin_obrigatorio
def dashboard():
    status = {"mongo": _medir(mongo.ping), "supabase": _medir(supabase.ping), "redis": _medir(redis_store.ping)}
    resumo = mongo.resumo() if status["mongo"]["ok"] else {}
    vendas, pedidos, acessos = {}, [], []
    if status["supabase"]["ok"]:
        vendas = supabase.resumo_vendas()
        pedidos = supabase.listar_pedidos(limite=5)
        acessos = supabase.ultimos_acessos(6)
    mais_vistos, cache = [], {}
    if status["redis"]["ok"]:
        ranking = redis_store.mais_vistos(5)
        produtos = {p["id"]: p for p in mongo.por_ids([pid for pid, _ in ranking])} if status["mongo"]["ok"] else {}
        mais_vistos = [{**produtos[pid], "views": int(v)} for pid, v in ranking if pid in produtos]
        cache = redis_store.estatisticas()
    return render_template("admin/dashboard.html", status=status, resumo=resumo, vendas=vendas,
                           pedidos=pedidos, acessos=acessos, mais_vistos=mais_vistos, cache=cache,
                           eventos=list(redis_store.eventos)[:10], modo=supabase.modo_auth(),
                           status_pedido=STATUS_PEDIDO)


# ---------------------------------------------------------------- produtos

@bp.get("/produtos")
@admin_obrigatorio
def produtos():
    q = (request.args.get("q") or "").strip()
    categoria = request.args.get("categoria") or None
    itens = mongo.listar_admin(q or None, categoria)
    return render_template("admin/produtos.html", itens=itens, q=q, categoria=categoria,
                           categorias=mongo.CATEGORIAS, novo=request.args.get("novo"))


def _form_vazio():
    return {"nome": "", "descricao": "", "categoria": "Roupas", "genero": "Unissex", "preco": "",
            "preco_promocional": "", "estoque": 10, "material": "", "composicao": "", "cores": [],
            "tamanhos": [], "imagens": [], "atributos": {}, "destaques": {}, "ativo": True}


def _ler_formulario():
    """Valida o formulário e devolve (dados para o MongoDB, erros, dados para reexibir)."""
    f = request.form
    erros = {}
    nome = (f.get("nome") or "").strip()
    if not 2 <= len(nome) <= 120:
        erros["nome"] = "Informe um nome entre 2 e 120 caracteres."
    categoria = f.get("categoria")
    if categoria not in mongo.CATEGORIAS:
        erros["categoria"] = "Escolha uma categoria."
    genero = f.get("genero") if f.get("genero") in mongo.GENEROS else "Unissex"
    try:
        preco = ler_preco(f.get("preco"))
        if not preco or preco <= 0:
            raise ValueError
    except ValueError:
        preco = None
        erros["preco"] = "Informe um preço maior que zero (ex.: 129,90)."
    try:
        promo = ler_preco(f.get("preco_promocional"))
        if promo is not None and preco and not 0 < promo < preco:
            erros["preco_promocional"] = "O preço promocional precisa ser menor que o preço normal."
    except ValueError:
        promo = None
        erros["preco_promocional"] = "Valor inválido."
    try:
        estoque = int(f.get("estoque") or 0)
        if estoque < 0:
            raise ValueError
    except ValueError:
        estoque = 0
        erros["estoque"] = "Informe um número inteiro (0 ou mais)."

    cores = []
    for cor_nome, cor_hex in zip(f.getlist("cor_nome"), f.getlist("cor_hex")):
        if cor_nome.strip():
            hexa = cor_hex if re.fullmatch(r"#[0-9a-fA-F]{6}", cor_hex or "") else "#cccccc"
            cores.append({"nome": cor_nome.strip()[:30], "hex": hexa.lower()})
    tamanhos = [t for t in mongo.TAMANHOS if t in f.getlist("tamanhos")]

    atributos = {}
    for chave, valor in zip(f.getlist("attr_nome"), f.getlist("attr_valor")):
        chave, valor = chave.strip()[:40], valor.strip()[:200]
        if chave and valor and "." not in chave and not chave.startswith("$"):
            atributos[chave] = valor

    imagens = [u for u in f.getlist("imagens_mantidas") if u.startswith(("/static/", "/imagem/", "https://"))]
    url_nova = (f.get("imagem_url") or "").strip()
    if url_nova:
        if re.match(r"^https://[^\s\"'<>]+$", url_nova):
            imagens.append(url_nova)
        else:
            erros["imagem_url"] = "Use um link que comece com https://"
    for arquivo in request.files.getlist("imagens_novas"):
        if not arquivo or not arquivo.filename:
            continue
        try:
            img = Image.open(arquivo.stream)
            img.verify()
            arquivo.stream.seek(0)
            img = Image.open(arquivo.stream).convert("RGB")
            img.thumbnail((1400, 1400))
            saida = io.BytesIO()
            img.save(saida, "JPEG", quality=85, optimize=True, progressive=True)
            imagens.append("/imagem/" + mongo.salvar_imagem(saida.getvalue(), arquivo.filename[:80], "image/jpeg"))
        except (UnidentifiedImageError, OSError):
            erros["imagens"] = f"“{arquivo.filename}” não é uma imagem válida."
    if not imagens and "imagens" not in erros:
        erros["imagens"] = "Adicione pelo menos uma foto do produto."

    dados = {
        "nome": nome, "descricao": (f.get("descricao") or "").strip()[:3000], "categoria": categoria,
        "genero": genero, "preco": preco, "preco_promocional": promo, "estoque": estoque,
        "material": (f.get("material") or "").strip()[:40], "composicao": (f.get("composicao") or "").strip()[:300],
        "cores": cores, "tamanhos": tamanhos, "imagens": imagens[:8], "atributos": atributos,
        "destaques": {k: k in f.getlist("destaques") for k in ("oferta", "queridinho", "novidade")},
        "ativo": f.get("ativo") == "on",
    }
    reexibir = {**dados, "preco": f.get("preco", ""), "preco_promocional": f.get("preco_promocional", "")}
    return dados, erros, reexibir


@bp.route("/produtos/novo", methods=["GET", "POST"])
@admin_obrigatorio
def novo_produto():
    if request.method == "POST":
        dados, erros, reexibir = _ler_formulario()
        if not erros:
            produto_id = mongo.criar(dados)
            redis_store.invalidar_cache()
            flash(f"“{dados['nome']}” cadastrado no MongoDB e já visível na loja.", "ok")
            return redirect(url_for("admin.produtos", novo=produto_id))
        flash("Confira os campos destacados.", "erro")
        return render_template("admin/form.html", p=reexibir, erros=erros, editando=False,
                               mongo=mongo), 400
    return render_template("admin/form.html", p=_form_vazio(), erros={}, editando=False, mongo=mongo)


@bp.route("/produtos/<produto_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def editar_produto(produto_id):
    atual = mongo.por_id(produto_id)
    if not atual:
        flash("Produto não encontrado.", "erro")
        return redirect(url_for("admin.produtos"))
    if request.method == "POST":
        dados, erros, reexibir = _ler_formulario()
        if not erros:
            removidas = set(atual["imagens"]) - set(dados["imagens"])
            mongo.atualizar(produto_id, dados)
            for url in removidas:
                if url.startswith("/imagem/"):
                    mongo.apagar_imagem(url.rsplit("/", 1)[-1])
            redis_store.invalidar_cache()
            flash(f"“{dados['nome']}” atualizado.", "ok")
            return redirect(url_for("admin.produtos", novo=produto_id))
        flash("Confira os campos destacados.", "erro")
        return render_template("admin/form.html", p={**reexibir, "id": produto_id}, erros=erros,
                               editando=True, mongo=mongo), 400
    return render_template("admin/form.html", p=atual, erros={}, editando=True, mongo=mongo)


@bp.post("/produtos/<produto_id>/excluir")
@admin_obrigatorio
def excluir_produto(produto_id):
    ok = mongo.excluir(produto_id)
    if ok:
        redis_store.invalidar_cache()
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=ok), (200 if ok else 404)
    flash("Produto excluído." if ok else "Produto não encontrado.", "ok" if ok else "erro")
    return redirect(url_for("admin.produtos"))


@bp.post("/produtos/<produto_id>/ativo")
@admin_obrigatorio
def alternar_ativo(produto_id):
    ativo = mongo.alternar_ativo(produto_id)
    if ativo is None:
        return jsonify(erro="Produto não encontrado."), 404
    redis_store.invalidar_cache()
    return jsonify(ativo=ativo)


@bp.get("/produtos/<produto_id>/documento")
@admin_obrigatorio
def documento(produto_id):
    doc = mongo.documento_bruto(produto_id)
    if not doc:
        return jsonify(erro="Produto não encontrado."), 404
    return jsonify(json=json.dumps(doc, ensure_ascii=False, indent=2, default=str))


# ---------------------------------------------------------------- pedidos e configurações

@bp.get("/pedidos")
@admin_obrigatorio
def pedidos():
    status = request.args.get("status") if request.args.get("status") in STATUS_PEDIDO else None
    try:
        itens, erro = supabase.listar_pedidos(limite=100, status=status), None
    except Exception:
        itens, erro = [], "Não foi possível ler os pedidos no Supabase."
    return render_template("admin/pedidos.html", pedidos=itens, erro=erro, status=status,
                           status_pedido=STATUS_PEDIDO)


@bp.post("/pedidos/<int:pedido_id>/status")
@admin_obrigatorio
def status_pedido(pedido_id):
    novo = (request.get_json(silent=True) or {}).get("status")
    if novo not in STATUS_PEDIDO:
        return jsonify(erro="Status inválido."), 400
    supabase.alterar_status(pedido_id, novo)
    return jsonify(ok=True, rotulo=STATUS_PEDIDO[novo])


@bp.route("/configuracoes", methods=["GET", "POST"])
@admin_obrigatorio
def configuracoes():
    erros = {}
    if request.method == "POST":
        numero = re.sub(r"\D", "", request.form.get("whatsapp_numero") or "")
        valores = {
            "loja_nome": (request.form.get("loja_nome") or "NOMA").strip()[:40],
            "whatsapp_numero": numero,
            "faixa_promocional": (request.form.get("faixa_promocional") or "").strip()[:60],
            "faixa_termina_em": (request.form.get("faixa_termina_em") or "").strip()[:19],
        }
        if not 12 <= len(numero) <= 13:
            erros["whatsapp_numero"] = "Use DDI + DDD + número, só dígitos (ex.: 5583999998888)."
        if not erros:
            supabase.salvar_configuracoes(valores)
            redis_store.invalidar_cache()
            flash("Configurações salvas no Supabase.", "ok")
            return redirect(url_for("admin.configuracoes"))
        return render_template("admin/configuracoes.html", c=valores, erros=erros), 400
    return render_template("admin/configuracoes.html", c=config_loja(), erros=erros)
