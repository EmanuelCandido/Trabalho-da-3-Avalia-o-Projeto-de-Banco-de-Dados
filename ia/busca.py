"""Busca semântica: texto -> vetor (Gemini) -> trechos mais parecidos (pgvector) -> dados atuais (MongoDB).

Também aplica filtros estruturados tirados da pergunta (busca híbrida simples):
"até R$ 200" vira preço máximo e "masculino", "pro meu pai" vira gênero. O vetor entende o significado,
mas não sabe comparar números; por isso o preço é conferido depois, com o valor atual do MongoDB.
"""
import hashlib
import re
import time

from bancos import mongo, redis_store, vetorial
from ia import gemini

LIMIAR = 0.6          # sobrescrito pelo RAG_LIMIAR do .env em init()
TOP_K = 6

_UNIDADES = {"dia", "dias", "cm", "centimetro", "centimetros", "centímetro", "centímetros", "kg", "quilo", "quilos",
             "vez", "vezes", "x", "hora", "horas", "h", "mes", "mês", "meses", "ano", "anos", "%", "peça", "peças",
             "unidade", "unidades", "metro", "metros", "m", "semana", "semanas", "minuto", "minutos"}
_NUMERO = r"(\d{1,5}(?:[.,]\d{1,2})?)"
_PRECO_MAX = re.compile(r"\b(?:até|ate|menos de|abaixo de|no máximo|no maximo|máximo de|maximo de|por no máximo)\s*"
                        r"(r\$\s*)?" + _NUMERO + r"\s*([a-zà-ú%$]+)?", re.I)
_PRECO_MIN = re.compile(r"\b(?:acima de|mais de|a partir de|pelo menos)\s*(r\$\s*)?" + _NUMERO + r"\s*([a-zà-ú%$]+)?",
                        re.I)
_MASCULINO = re.compile(r"\b(masculin[oa]s?|homem|homens|rapaz|para ele|pra ele|meu (?:pai|marido|namorado|irmão|"
                        r"irmao|filho|avô|avo|tio|amigo|chefe))\b", re.I)
_FEMININO = re.compile(r"\b(feminin[oa]s?|mulher|mulheres|moça|para ela|pra ela|minha (?:mãe|mae|esposa|namorada|"
                       r"irmã|irma|filha|avó|tia|amiga|chefe))\b", re.I)


def init(limiar, top_k):
    global LIMIAR, TOP_K
    LIMIAR, TOP_K = float(limiar), int(top_k)


# ---------------------------------------------------------------- filtros estruturados

def _valor_em_reais(match):
    cifrao, numero, depois = match.group(1), match.group(2), (match.group(3) or "").lower()
    if depois in _UNIDADES:
        return None  # "até 30 dias", "até 3 peças": não é preço
    valor = float(numero.replace(".", "").replace(",", ".") if "," in numero else numero)
    if not cifrao and depois not in ("reais", "real", "conto", "contos") and valor < 20:
        return None  # número pequeno sem "R$" nem "reais": provavelmente não é preço
    return valor


def extrair_filtros(pergunta):
    """{'preco_max': 200.0, 'preco_min': None, 'genero': 'Masculino'} (só o que a pergunta disser)."""
    filtros = {}
    for m in _PRECO_MAX.finditer(pergunta):
        valor = _valor_em_reais(m)
        if valor:
            filtros["preco_max"] = valor
    for m in _PRECO_MIN.finditer(pergunta):
        valor = _valor_em_reais(m)
        if valor:
            filtros["preco_min"] = valor
    masc, fem = bool(_MASCULINO.search(pergunta)), bool(_FEMININO.search(pergunta))
    if masc != fem:
        filtros["genero"] = "Masculino" if masc else "Feminino"
    return filtros


def _motivo_descarte(produto, filtros):
    if filtros.get("preco_max") is not None and produto["preco_final"] > filtros["preco_max"]:
        return f"preço acima de R$ {filtros['preco_max']:.0f}"
    if filtros.get("preco_min") is not None and produto["preco_final"] < filtros["preco_min"]:
        return f"preço abaixo de R$ {filtros['preco_min']:.0f}"
    if filtros.get("genero") and produto["genero"] not in (filtros["genero"], "Unissex"):
        return f"não é {filtros['genero'].lower()}"
    return None


# ---------------------------------------------------------------- vetor da pergunta (com cache no Redis)

def vetor_da_pergunta(texto):
    """Devolve (vetor, ms, veio_do_cache). A mesma pergunta não chama a API de novo por 7 dias."""
    inicio = time.perf_counter()
    chave = hashlib.sha1(f"{gemini.modelo_embedding()}|{texto.strip().lower()}".encode()).hexdigest()
    try:
        guardado = redis_store.embedding_guardado(chave)
    except Exception:
        guardado = None
    if guardado:
        return guardado, round((time.perf_counter() - inicio) * 1000), True
    vetor = gemini.embedding(texto, "RETRIEVAL_QUERY")
    try:
        redis_store.guardar_embedding(chave, vetor)
    except Exception:
        pass
    return vetor, round((time.perf_counter() - inicio) * 1000), False


# ---------------------------------------------------------------- busca

def buscar(consulta, k=None, filtros=None, produto_id=None, fontes=None):
    """Busca vetorial completa. Devolve todos os candidatos, com o motivo quando um deles é descartado
    (o laboratório do painel mostra os dois grupos)."""
    k = k or TOP_K
    filtros = filtros if filtros is not None else extrair_filtros(consulta)
    vetor, ms_embedding, do_cache = vetor_da_pergunta(consulta)

    inicio = time.perf_counter()
    linhas = vetorial.buscar(vetor, qtd=min(k * 2 + 4, 20), fontes=fontes)
    if produto_id:  # chat aberto na página de um produto: os trechos dele sempre entram como candidatos
        ja = {r["id"] for r in linhas}
        linhas += [r for r in vetorial.trechos_de(str(produto_id), vetor) if r["id"] not in ja]
        linhas.sort(key=lambda r: r["similaridade"], reverse=True)
    ms_busca = round((time.perf_counter() - inicio) * 1000)

    # Preço, estoque, fotos e link vêm do MongoDB agora (não estão no vetor).
    refs = list({r["referencia"] for r in linhas if r["fonte"] in ("produto", "avaliacao")})
    produtos = {p["id"]: p for p in mongo.por_ids(refs)} if refs else {}

    trechos, aceitos = [], 0
    for r in linhas:
        t = {**r, "similaridade": round(float(r["similaridade"]), 4), "produto": None, "descartado": None}
        if r["fonte"] in ("produto", "avaliacao"):
            t["produto"] = produtos.get(r["referencia"])
            if not t["produto"]:
                t["descartado"] = "produto inativo ou excluído"
            else:
                t["descartado"] = _motivo_descarte(t["produto"], filtros)
        fixo = produto_id and r["referencia"] == str(produto_id)
        if not t["descartado"] and t["similaridade"] < LIMIAR and not fixo:
            t["descartado"] = f"abaixo do limiar ({LIMIAR:.2f})"
        if not t["descartado"]:
            if aceitos >= k:
                t["descartado"] = f"fora do top {k}"
            else:
                aceitos += 1
        trechos.append(t)

    return {"consulta": consulta, "filtros": filtros, "vetor": vetor, "vetor_do_cache": do_cache,
            "trechos": trechos, "aceitos": [t for t in trechos if not t["descartado"]],
            "melhor_similaridade": max((t["similaridade"] for t in trechos), default=0.0),
            "ms_embedding": ms_embedding, "ms_busca": ms_busca, "limiar": LIMIAR, "k": k}


def ids_semelhantes(consulta, limite=24):
    """Para a página /busca: ids de produtos por ordem de significado (produto ou avaliações dele)."""
    r = buscar(consulta, k=20, fontes=["produto", "avaliacao"])
    vistos, ids = set(), []
    for t in r["aceitos"]:
        if t["referencia"] not in vistos:
            vistos.add(t["referencia"])
            ids.append(t["referencia"])
    return ids[:limite], r


def parecidos(produto_id, qtd=4):
    """'Você também pode gostar': vizinhos do vetor do produto no pgvector (não chama a API).
    Sem vetores (IA desligada ou produto ainda não indexado), usa a mesma categoria."""
    try:
        ids = [r["referencia"] for r in vetorial.parecidos(str(produto_id), qtd + 2)]
    except Exception:
        ids = []
    itens = [p for p in mongo.por_ids(ids) if p["id"] != str(produto_id)][:qtd] if ids else []
    if itens:
        return itens
    p = mongo.por_id(produto_id, completo=False)
    if not p:
        return []
    lista, _ = mongo.listar(mongo.montar_filtro(categoria=p["categoria"]), "mais-vendidos", qtd + 1)
    return [x for x in lista if x["id"] != p["id"]][:qtd]
