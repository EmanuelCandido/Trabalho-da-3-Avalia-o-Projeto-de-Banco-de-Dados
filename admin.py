"""Módulo administrativo (restrito): login pelo Supabase, cadastro de produtos no MongoDB e painel."""
import io
import json
import re
import secrets
from datetime import datetime, timezone
from time import perf_counter

from flask import (Blueprint, flash, jsonify, redirect, render_template, request, session, url_for)
from PIL import Image, UnidentifiedImageError

from bancos import mongo, redis_store, supabase
from utils import (admin_obrigatorio, config_loja, ip_cliente, ler_data_hora, ler_preco,
                   mostrar_data_hora)

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
            img.thumbnail((1200, 1200))
            saida = io.BytesIO()
            img.save(saida, "WEBP", quality=80, method=4)  # WebP: bem mais leve que JPEG
            imagens.append("/imagem/" + mongo.salvar_imagem(saida.getvalue(), arquivo.filename[:80], "image/webp"))
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


# ---------------------------------------------------------------- vitrine: banners do carrossel e faixa do topo

COR_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LINKS_PRONTOS = [("/ofertas", "Ofertas da Black"), ("/novidades", "Novidades"), ("/roupas", "Roupas"),
                 ("/acessorios", "Acessórios"), ("/sobre", "Sobre a NOMA"), ("/atendimento", "Atendimento")]


def _status_banner(b, agora):
    inicio = datetime.fromisoformat(b["inicio"]) if b.get("inicio") else None
    fim = datetime.fromisoformat(b["fim"]) if b.get("fim") else None
    if not b.get("ativo"):
        return "desligado", "Desligado"
    if inicio and inicio > agora:
        return "agendado", "Agendado"
    if fim and fim <= agora:
        return "encerrado", "Encerrado"
    return "no_ar", "No ar"


def _salvar_foto(arquivo, largura):
    """Converte a foto enviada para WebP no tamanho certo e grava no GridFS. Devolve a URL ou levanta ValueError."""
    try:
        img = Image.open(arquivo.stream)
        img.verify()
        arquivo.stream.seek(0)
        img = Image.open(arquivo.stream).convert("RGB")
    except (UnidentifiedImageError, OSError) as erro:
        raise ValueError(f"“{arquivo.filename}” não é uma imagem válida.") from erro
    img.thumbnail((largura, largura * 2))
    saida = io.BytesIO()
    img.save(saida, "WEBP", quality=78, method=4)
    return "/imagem/" + mongo.salvar_imagem(saida.getvalue(), arquivo.filename[:80], "image/webp")


@bp.get("/vitrine")
@admin_obrigatorio
def vitrine():
    agora = datetime.now(timezone.utc)
    lista = []
    for b in mongo.listar_banners():
        codigo, rotulo = _status_banner(b, agora)
        lista.append({**b, "status": codigo, "status_rotulo": rotulo,
                      "inicio_txt": mostrar_data_hora(b.get("inicio")), "fim_txt": mostrar_data_hora(b.get("fim"))})
    c = config_loja()
    c = {**c, "faixa_termina_txt": mostrar_data_hora(c.get("faixa_termina_em"))}
    erros = dict.fromkeys((request.args.get("erro") or "").split(","), True)
    return render_template("admin/vitrine.html", banners=lista, c=c, erros=erros, maximo=mongo.MAX_BANNERS,
                           no_ar=sum(1 for b in lista if b["status"] == "no_ar"))


@bp.post("/vitrine/faixa")
@admin_obrigatorio
def salvar_faixa():
    f = request.form
    erros = {}
    texto = (f.get("faixa_promocional") or "").strip()[:70]
    link = (f.get("faixa_link") or "").strip()[:200]
    if link and not (link.startswith("/") or link.startswith("https://")):
        erros["faixa_link"] = "Use um endereço da loja (ex.: /ofertas) ou um link https://"
    try:
        termina = ler_data_hora(f.get("faixa_termina_em"))
    except ValueError:
        termina, erros["faixa_termina_em"] = None, "Use o formato dd/mm/aaaa hh:mm."
    cores = {k: f.get(k, "") for k in ("faixa_cor_fundo", "faixa_cor_texto")}
    for k, v in cores.items():
        if not COR_HEX.match(v):
            erros[k] = "Cor inválida."
    if f.get("faixa_ativa") == "on" and not texto:
        erros["faixa_promocional"] = "Escreva o texto da faixa (ou desligue a faixa)."
    if erros:
        flash(" ".join(erros.values()), "erro")
        return redirect(url_for("admin.vitrine", erro=",".join(erros)) + "#faixa")
    supabase.salvar_configuracoes({
        "faixa_ativa": "1" if f.get("faixa_ativa") == "on" else "0",
        "faixa_promocional": texto, "faixa_link": link,
        "faixa_contagem": "1" if f.get("faixa_contagem") == "on" else "0",
        "faixa_termina_em": termina.isoformat() if termina else "", **cores,
    })
    redis_store.invalidar_cache()
    flash("Faixa do topo salva no Supabase.", "ok")
    return redirect(url_for("admin.vitrine") + "#faixa")


@bp.post("/vitrine/carrossel")
@admin_obrigatorio
def salvar_carrossel():
    try:
        tempo = min(20, max(3, int(request.form.get("carrossel_tempo") or 6)))
    except ValueError:
        tempo = 6
    supabase.salvar_configuracoes({
        "carrossel_tempo": str(tempo),
        "carrossel_automatico": "1" if request.form.get("carrossel_automatico") == "on" else "0"})
    redis_store.invalidar_cache()
    flash("Carrossel atualizado.", "ok")
    return redirect(url_for("admin.vitrine") + "#carrossel")


def _ler_banner(atual=None):
    f = request.form
    erros = {}
    titulo = (f.get("titulo") or "").strip()[:60]
    if len(titulo) < 2:
        erros["titulo"] = "Escreva o título do banner."
    botao_texto = (f.get("botao_texto") or "").strip()[:24]
    botao_link = (f.get("botao_link") or "").strip()[:200]
    if botao_texto and not (botao_link.startswith("/") or botao_link.startswith("https://")):
        erros["botao_link"] = "Escolha para onde o botão leva (ex.: /ofertas)."
    cor = f.get("cor_fundo", "#1d3a52")
    if not COR_HEX.match(cor):
        erros["cor_fundo"] = "Cor inválida."
    try:
        inicio = ler_data_hora(f.get("inicio"))
    except ValueError:
        inicio, erros["inicio"] = None, "Use dd/mm/aaaa hh:mm."
    try:
        fim = ler_data_hora(f.get("fim"))
    except ValueError:
        fim, erros["fim"] = None, "Use dd/mm/aaaa hh:mm."
    if inicio and fim and fim <= inicio:
        erros["fim"] = "O fim precisa ser depois do início."

    imagens = {"imagem": (atual or {}).get("imagem"), "imagem_celular": (atual or {}).get("imagem_celular")}
    for campo, largura in (("imagem", 1920), ("imagem_celular", 900)):
        if f.get(f"remover_{campo}") == "1":
            imagens[campo] = None
        arquivo = request.files.get(campo)
        if arquivo and arquivo.filename:
            try:
                imagens[campo] = _salvar_foto(arquivo, largura)
            except ValueError as erro:
                erros[campo] = str(erro)
    if not imagens["imagem"] and "imagem" not in erros:
        erros["imagem"] = "Envie a imagem para computador."

    dados = {
        "chapeu": (f.get("chapeu") or "").strip()[:40], "titulo": titulo,
        "subtitulo": (f.get("subtitulo") or "").strip()[:80],
        "botao_texto": botao_texto, "botao_link": botao_link if botao_texto else "",
        "cor_fundo": cor.lower(), "tema": "escuro" if f.get("tema") == "escuro" else "claro",
        "alinhamento": "centro" if f.get("alinhamento") == "centro" else "esquerda",
        "inicio": inicio, "fim": fim, "ativo": f.get("ativo") == "on", **imagens,
    }
    return dados, erros


def _form_banner(b, erros, editando):
    b = {**b, "inicio_txt": b.get("inicio_txt") or mostrar_data_hora(b.get("inicio")),
         "fim_txt": b.get("fim_txt") or mostrar_data_hora(b.get("fim"))}
    return render_template("admin/banner.html", b=b, erros=erros, editando=editando, links=LINKS_PRONTOS)


@bp.route("/vitrine/banners/novo", methods=["GET", "POST"])
@admin_obrigatorio
def novo_banner():
    if request.method == "POST":
        dados, erros = _ler_banner()
        if not erros:
            if mongo.contar_banners()[0] >= mongo.MAX_BANNERS:
                flash(f"Limite de {mongo.MAX_BANNERS} banners. Exclua um antes de criar outro.", "erro")
                return redirect(url_for("admin.vitrine"))
            mongo.salvar_banner(dados)
            redis_store.invalidar_cache()
            flash("Banner criado e salvo no MongoDB.", "ok")
            return redirect(url_for("admin.vitrine") + "#banners")
        flash("Confira os campos destacados.", "erro")
        return _form_banner({**dados, "inicio_txt": request.form.get("inicio"), "fim_txt": request.form.get("fim")},
                            erros, False), 400
    vazio = {"chapeu": "", "titulo": "", "subtitulo": "", "botao_texto": "Ver mais", "botao_link": "/ofertas",
             "cor_fundo": "#1d3a52", "tema": "claro", "alinhamento": "esquerda", "ativo": True,
             "imagem": None, "imagem_celular": None}
    return _form_banner(vazio, {}, False)


@bp.route("/vitrine/banners/<banner_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def editar_banner(banner_id):
    atual = mongo.banner_por_id(banner_id)
    if not atual:
        flash("Banner não encontrado.", "erro")
        return redirect(url_for("admin.vitrine"))
    if request.method == "POST":
        dados, erros = _ler_banner(atual)
        if not erros:
            for campo in ("imagem", "imagem_celular"):
                antiga = atual.get(campo) or ""
                if antiga != dados[campo] and antiga.startswith("/imagem/"):
                    mongo.apagar_imagem(antiga.rsplit("/", 1)[-1])
            mongo.salvar_banner(dados, banner_id)
            redis_store.invalidar_cache()
            flash("Banner atualizado.", "ok")
            return redirect(url_for("admin.vitrine") + "#banners")
        flash("Confira os campos destacados.", "erro")
        return _form_banner({**dados, "id": banner_id, "inicio_txt": request.form.get("inicio"),
                             "fim_txt": request.form.get("fim")}, erros, True), 400
    return _form_banner(atual, {}, True)


@bp.post("/vitrine/banners/<banner_id>/excluir")
@admin_obrigatorio
def excluir_banner(banner_id):
    ok = mongo.excluir_banner(banner_id)
    redis_store.invalidar_cache()
    return jsonify(ok=ok), (200 if ok else 404)


@bp.post("/vitrine/banners/<banner_id>/ativo")
@admin_obrigatorio
def alternar_banner(banner_id):
    ativo = mongo.alternar_banner(banner_id)
    if ativo is None:
        return jsonify(erro="Banner não encontrado."), 404
    redis_store.invalidar_cache()
    return jsonify(ativo=ativo)


@bp.post("/vitrine/banners/ordem")
@admin_obrigatorio
def ordenar_banners():
    ids = (request.get_json(silent=True) or {}).get("ids") or []
    mongo.ordenar_banners([str(i) for i in ids][:mongo.MAX_BANNERS * 2])
    redis_store.invalidar_cache()
    return jsonify(ok=True)
