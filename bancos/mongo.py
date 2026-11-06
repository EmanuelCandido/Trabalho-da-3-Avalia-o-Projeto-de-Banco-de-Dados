"""MongoDB: cadastro e armazenamento dos produtos (documentos flexíveis) e das imagens (GridFS)."""
import re
import unicodedata
from datetime import datetime, timezone

import gridfs
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import PyMongoError

CATEGORIAS = ["Roupas", "Acessórios"]
GENEROS = ["Feminino", "Masculino", "Unissex"]
TAMANHOS = ["PP", "P", "M", "G", "GG", "XGG", "Único"]
ORDENS = {
    # "posicao" é a ordem de vitrine do seed; produtos novos do admin não têm posição e aparecem primeiro.
    "relevancia": [("posicao", ASCENDING), ("vendidos", DESCENDING)],
    "mais-vendidos": [("vendidos", DESCENDING)],
    "menor-preco": [("preco_final", ASCENDING)],
    "maior-preco": [("preco_final", DESCENDING)],
    "novidades": [("criado_em", DESCENDING)],
}
FAIXAS_PRECO = {
    "ate-150": (0, 150),
    "150-300": (150, 300),
    "300-500": (300, 500),
    "acima-500": (500, None),
}

_cliente = None
_db = None


def init(uri, nome_db):
    """Abre a conexão (uma vez) e garante os índices."""
    global _cliente, _db
    _cliente = MongoClient(uri, serverSelectionTimeoutMS=8000, tz_aware=True)
    _db = _cliente[nome_db]
    try:
        col = _db.produtos
        col.create_index("slug", unique=True)
        col.create_index([("nome", "text"), ("descricao", "text")], default_language="portuguese",
                         name="busca_texto")
        col.create_index([("ativo", ASCENDING), ("categoria", ASCENDING)])
        col.create_index("destaques.oferta")
        col.create_index("destaques.queridinho")
        col.create_index("destaques.novidade")
    except PyMongoError:
        # Sem rede no momento da subida: as telas mostram o erro e o índice é criado na próxima vez.
        pass


def produtos():
    return _db.produtos


def _fs():
    return gridfs.GridFS(_db, collection="imagens")


def ping():
    _cliente.admin.command("ping")
    return True


# ---------------------------------------------------------------- utilidades

def slugify(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()
    return texto or "produto"


def _oid(valor):
    try:
        return ObjectId(str(valor))
    except (InvalidId, TypeError):
        return None


def _agora():
    return datetime.now(timezone.utc)


def serializar(doc, completo=False):
    """Converte o documento para o formato usado pelas telas (e pelo cache em JSON)."""
    if not doc:
        return None
    preco = float(doc.get("preco") or 0)
    promo = doc.get("preco_promocional")
    promo = float(promo) if promo not in (None, "") else None
    final = promo if promo is not None and promo < preco else preco
    avaliacoes = doc.get("avaliacoes") or []
    notas = [int(a.get("nota", 0)) for a in avaliacoes]
    item = {
        "id": str(doc["_id"]),
        "slug": doc.get("slug"),
        "nome": doc.get("nome"),
        "categoria": doc.get("categoria"),
        "genero": doc.get("genero"),
        "preco": preco,
        "preco_promocional": promo,
        "preco_final": final,
        "desconto_pct": round((1 - final / preco) * 100) if preco and final < preco else 0,
        "estoque": int(doc.get("estoque") or 0),
        "vendidos": int(doc.get("vendidos") or 0),
        "cores": doc.get("cores") or [],
        "tamanhos": doc.get("tamanhos") or [],
        "imagens": doc.get("imagens") or [],
        "destaques": doc.get("destaques") or {},
        "ativo": bool(doc.get("ativo", True)),
        "nota_media": round(sum(notas) / len(notas), 1) if notas else None,
        "total_avaliacoes": len(notas),
    }
    if completo:
        # Lista (e não dicionário) porque o JSON do cache no Redis transformaria as chaves em texto.
        dist = [{"nota": n, "qtd": notas.count(n)} for n in range(5, 0, -1)]
        item.update({
            "descricao": doc.get("descricao") or "",
            "material": doc.get("material") or "",
            "composicao": doc.get("composicao") or "",
            "atributos": doc.get("atributos") or {},
            "avaliacoes": [
                {**{k: v for k, v in a.items() if k != "data"},
                 "data": a["data"].isoformat() if isinstance(a.get("data"), datetime) else a.get("data")}
                for a in sorted(avaliacoes, key=lambda a: a.get("data") or _agora(), reverse=True)
            ],
            "distribuicao": dist,
            "criado_em": doc["criado_em"].isoformat() if isinstance(doc.get("criado_em"), datetime) else None,
            "atualizado_em": doc["atualizado_em"].isoformat() if isinstance(doc.get("atualizado_em"), datetime) else None,
        })
    return item


# ---------------------------------------------------------------- leitura (loja)

def montar_filtro(categoria=None, genero=None, tamanho=None, cor=None, preco=None, material=None,
                  q=None, destaque=None, incluir_inativos=False):
    filtro = {} if incluir_inativos else {"ativo": True}
    if categoria:
        filtro["categoria"] = categoria
    if genero:
        filtro["genero"] = {"$in": [genero, "Unissex"]}
    if tamanho:
        filtro["tamanhos"] = tamanho
    if cor:
        filtro["cores.nome"] = cor
    if material:
        filtro["material"] = material
    if destaque in ("oferta", "queridinho", "novidade"):
        filtro[f"destaques.{destaque}"] = True
    if preco in FAIXAS_PRECO:
        minimo, maximo = FAIXAS_PRECO[preco]
        filtro["preco_final"] = {"$gte": minimo, **({"$lt": maximo} if maximo else {})}
    if q:
        termo = re.escape(q.strip())
        filtro["$or"] = [{"nome": {"$regex": termo, "$options": "i"}},
                         {"categoria": {"$regex": termo, "$options": "i"}},
                         {"material": {"$regex": termo, "$options": "i"}},
                         {"cores.nome": {"$regex": termo, "$options": "i"}}]
    return filtro


def listar(filtro, ordem="relevancia", limite=12, pular=0):
    cursor = (produtos().find(filtro, {"descricao": 0, "avaliacoes.texto": 0})
              .sort(ORDENS.get(ordem, ORDENS["relevancia"])).skip(pular).limit(limite))
    itens = [serializar(d) for d in cursor]
    return itens, produtos().count_documents(filtro)


def opcoes_filtro(categoria=None):
    """Valores existentes para montar os filtros da listagem (aggregate com $group)."""
    base = {"ativo": True, **({"categoria": categoria} if categoria else {})}
    resultado = list(produtos().aggregate([
        {"$match": base},
        {"$facet": {
            "generos": [{"$group": {"_id": "$genero"}}],
            "tamanhos": [{"$unwind": "$tamanhos"}, {"$group": {"_id": "$tamanhos"}}],
            "cores": [{"$unwind": "$cores"}, {"$group": {"_id": "$cores.nome", "hex": {"$first": "$cores.hex"}}}],
            "materiais": [{"$group": {"_id": "$material"}}],
        }},
    ]))
    r = resultado[0] if resultado else {}
    tamanhos = {t["_id"] for t in r.get("tamanhos", []) if t["_id"]}
    return {
        "generos": sorted(g["_id"] for g in r.get("generos", []) if g["_id"] and g["_id"] != "Unissex"),
        "tamanhos": [t for t in TAMANHOS if t in tamanhos],
        "cores": sorted(({"nome": c["_id"], "hex": c.get("hex")} for c in r.get("cores", []) if c["_id"]),
                        key=lambda c: c["nome"]),
        "materiais": sorted(m["_id"] for m in r.get("materiais", []) if m["_id"]),
    }


def por_slug(slug):
    return serializar(produtos().find_one({"slug": slug, "ativo": True}), completo=True)


def por_id(produto_id, completo=True):
    oid = _oid(produto_id)
    return serializar(produtos().find_one({"_id": oid}), completo=completo) if oid else None


def por_ids(ids):
    """Busca vários produtos mantendo a ordem dos ids (usado pelos vistos recentemente)."""
    oids = [o for o in (_oid(i) for i in ids) if o]
    if not oids:
        return []
    docs = {str(d["_id"]): serializar(d) for d in produtos().find({"_id": {"$in": oids}, "ativo": True},
                                                                  {"descricao": 0})}
    return [docs[i] for i in ids if i in docs]


def sugestoes(q, limite=6):
    if not q or len(q.strip()) < 2:
        return []
    itens, _ = listar(montar_filtro(q=q), ordem="mais-vendidos", limite=limite)
    return itens


# ---------------------------------------------------------------- escrita (admin)

def _slug_unico(nome, ignorar_id=None):
    base = slugify(nome)
    slug, n = base, 2
    while produtos().find_one({"slug": slug, **({"_id": {"$ne": ignorar_id}} if ignorar_id else {})}):
        slug, n = f"{base}-{n}", n + 1
    return slug


def _preco_final(dados):
    promo = dados.get("preco_promocional")
    return promo if promo is not None and promo < dados["preco"] else dados["preco"]


def criar(dados):
    agora = _agora()
    doc = {**dados, "slug": _slug_unico(dados["nome"]), "preco_final": _preco_final(dados),
           "vendidos": int(dados.get("vendidos") or 0), "avaliacoes": dados.get("avaliacoes") or [],
           "criado_em": agora, "atualizado_em": agora}
    resultado = produtos().insert_one(doc)
    return str(resultado.inserted_id)


def atualizar(produto_id, dados):
    oid = _oid(produto_id)
    atual = produtos().find_one({"_id": oid}, {"nome": 1, "slug": 1})
    if not atual:
        return False
    campos = {**dados, "preco_final": _preco_final(dados), "atualizado_em": _agora()}
    if dados.get("nome") and dados["nome"] != atual.get("nome"):
        campos["slug"] = _slug_unico(dados["nome"], ignorar_id=oid)
    produtos().update_one({"_id": oid}, {"$set": campos})
    return True


def excluir(produto_id):
    oid = _oid(produto_id)
    doc = produtos().find_one_and_delete({"_id": oid})
    if doc:
        for url in doc.get("imagens") or []:
            if url.startswith("/imagem/"):
                apagar_imagem(url.rsplit("/", 1)[-1])
    return doc is not None


def alternar_ativo(produto_id):
    oid = _oid(produto_id)
    doc = produtos().find_one_and_update(
        {"_id": oid}, [{"$set": {"ativo": {"$not": "$ativo"}, "atualizado_em": _agora()}}],
        return_document=ReturnDocument.AFTER, projection={"ativo": 1})
    return doc["ativo"] if doc else None


def adicionar_avaliacao(slug, avaliacao):
    avaliacao = {**avaliacao, "data": _agora()}
    r = produtos().update_one({"slug": slug, "ativo": True}, {"$push": {"avaliacoes": avaliacao}})
    return r.modified_count == 1


def registrar_venda(itens):
    """Soma os vendidos e baixa o estoque quando o pedido é enviado ao WhatsApp."""
    for item in itens:
        oid = _oid(item["produto_id"])
        if oid:
            produtos().update_one({"_id": oid}, [{"$set": {
                "vendidos": {"$add": [{"$ifNull": ["$vendidos", 0]}, item["quantidade"]]},
                "estoque": {"$max": [0, {"$subtract": [{"$ifNull": ["$estoque", 0]}, item["quantidade"]]}]},
            }}])


def resumo():
    """Números do dashboard, calculados com aggregate."""
    r = list(produtos().aggregate([{"$group": {
        "_id": None,
        "total": {"$sum": 1},
        "ativos": {"$sum": {"$cond": ["$ativo", 1, 0]}},
        "sem_estoque": {"$sum": {"$cond": [{"$lte": ["$estoque", 0]}, 1, 0]}},
        "em_oferta": {"$sum": {"$cond": [{"$lt": ["$preco_final", "$preco"]}, 1, 0]}},
        "unidades": {"$sum": "$estoque"},
        "avaliacoes": {"$sum": {"$size": {"$ifNull": ["$avaliacoes", []]}}},
    }}]))
    base = {"total": 0, "ativos": 0, "sem_estoque": 0, "em_oferta": 0, "unidades": 0, "avaliacoes": 0}
    if r:
        base.update({k: v for k, v in r[0].items() if k != "_id"})
    return base


def listar_admin(q=None, categoria=None):
    filtro = montar_filtro(categoria=categoria, q=q, incluir_inativos=True)
    cursor = produtos().find(filtro, {"descricao": 0, "avaliacoes": 0}).sort("atualizado_em", DESCENDING)
    return [serializar(d) for d in cursor]


def documento_bruto(produto_id):
    """O documento como está no MongoDB (mostrado no admin para a apresentação)."""
    oid = _oid(produto_id)
    doc = produtos().find_one({"_id": oid})
    if not doc:
        return None
    doc["_id"] = f"ObjectId('{doc['_id']}')"
    for chave in ("criado_em", "atualizado_em"):
        if isinstance(doc.get(chave), datetime):
            doc[chave] = doc[chave].isoformat()
    for a in doc.get("avaliacoes", []):
        if isinstance(a.get("data"), datetime):
            a["data"] = a["data"].isoformat()
    return doc


# ---------------------------------------------------------------- imagens (GridFS)

def salvar_imagem(conteudo, nome, tipo):
    return str(_fs().put(conteudo, filename=nome, contentType=tipo, enviado_em=_agora()))


def ler_imagem(imagem_id):
    oid = _oid(imagem_id)
    if not oid:
        return None
    try:
        return _fs().get(oid)
    except gridfs.errors.NoFile:
        return None


def apagar_imagem(imagem_id):
    oid = _oid(imagem_id)
    if oid:
        try:
            _fs().delete(oid)
        except PyMongoError:
            pass
