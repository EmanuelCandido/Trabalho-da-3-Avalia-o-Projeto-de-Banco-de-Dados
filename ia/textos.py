"""Monta os textos que viram vetores e divide documentos em trechos (chunks).

Regra principal: só entra no texto o que tem SIGNIFICADO para a busca e muda pouco.
Preço exato e estoque ficam de fora (mudam a cada venda e promoção) e são lidos na hora do MongoDB
quando o trecho é recuperado. Só a faixa de preço entra, porque ajuda em "algo barato" e quase não muda.
"""
import hashlib
import re

MAX_AVALIACOES = 1500      # caracteres do texto de avaliações de um produto
MAX_TRECHO = 900           # tamanho máximo de um trecho de documento
SOBREPOSICAO = 150         # caracteres repetidos entre trechos vizinhos

FAIXAS = [(150, "até R$ 150"), (300, "de R$ 150 a R$ 300"), (500, "de R$ 300 a R$ 500"), (None, "acima de R$ 500")]
GENEROS = {"Masculino": "Masculino (para homens)", "Feminino": "Feminino (para mulheres)",
           "Unissex": "Unissex (serve para homens e mulheres)"}
DESTAQUES = {"oferta": "em oferta", "novidade": "novidade da coleção", "queridinho": "um dos queridinhos dos clientes"}


def hash_texto(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def faixa_preco(valor):
    for limite, rotulo in FAIXAS:
        if limite is None or valor < limite:
            return rotulo
    return FAIXAS[-1][1]


def _lista(itens):
    itens = [i for i in itens if i]
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


# ---------------------------------------------------------------- produtos

def texto_produto(p):
    """p: produto serializado com completo=True (bancos/mongo.py)."""
    tamanhos = [t for t in p["tamanhos"] if t != "Único"]
    destaques = [DESTAQUES[k] for k, ligado in (p.get("destaques") or {}).items() if ligado and k in DESTAQUES]
    linhas = [
        f"Produto: {p['nome']}",
        f"Categoria: {p['categoria']}. Gênero: {GENEROS.get(p['genero'], p['genero'])}.",
        f"Material: {p['material']}." if p.get("material") else "",
        f"Composição e cuidados: {p['composicao']}" if p.get("composicao") else "",
        f"Cores: {_lista([c['nome'] for c in p['cores']])}." if p["cores"] else "",
        f"Tamanhos: {_lista(tamanhos)}." if tamanhos else "Tamanho único.",
        f"Faixa de preço: {faixa_preco(p['preco_final'])}.",
        f"Destaques: {_lista(destaques)}." if destaques else "",
        f"Descrição: {p['descricao']}" if p.get("descricao") else "",
        ("Características: " + "; ".join(f"{k}: {v}" for k, v in p["atributos"].items()) + ".")
        if p.get("atributos") else "",
    ]
    return "\n".join(l for l in linhas if l)


def metadados_produto(p):
    return {"slug": p["slug"], "nome": p["nome"], "categoria": p["categoria"], "genero": p["genero"],
            "faixa": faixa_preco(p["preco_final"])}


def texto_avaliacoes(p):
    """As avaliações do produto juntas num texto só (ou None se não houver)."""
    avaliacoes = p.get("avaliacoes") or []
    if not avaliacoes:
        return None
    media = f"{p['nota_media']:.1f}".replace(".", ",") if p.get("nota_media") else "?"
    texto = (f"Avaliações de clientes sobre {p['nome']} (nota média {media} de 5, "
             f"{len(avaliacoes)} avaliação{'ões' if len(avaliacoes) > 1 else ''}):")
    for a in avaliacoes:
        detalhes = ", ".join(x for x in (f"tamanho {a['tamanho']}" if a.get("tamanho") else "",
                                         f"cor {a['cor']}" if a.get("cor") else "") if x)
        linha = (f"\n- {a.get('nome', 'Cliente')}, {a.get('nota', '?')} estrela(s)"
                 f"{', ' + detalhes if detalhes else ''}: \"{a.get('titulo', '')}\". {a.get('texto', '')}".rstrip())
        if len(texto) + len(linha) > MAX_AVALIACOES:
            break
        texto += linha
    return texto


# ---------------------------------------------------------------- documentos

def titulo_markdown(texto, padrao):
    """Primeira linha '# Título' do Markdown (ou o padrão)."""
    for linha in texto.splitlines():
        if linha.startswith("# "):
            return linha[2:].strip()
    return padrao


def _secoes(texto):
    """Divide o Markdown pelos títulos '## '. Devolve [(seção, corpo)]."""
    secoes, atual, corpo = [], "", []
    for linha in texto.splitlines():
        if linha.startswith("# "):
            continue
        if linha.startswith("## "):
            if "".join(corpo).strip():
                secoes.append((atual, "\n".join(corpo).strip()))
            atual, corpo = linha[3:].strip(), []
        else:
            corpo.append(linha)
    if "".join(corpo).strip():
        secoes.append((atual, "\n".join(corpo).strip()))
    return secoes


def _partes_pequenas(paragrafo, maximo):
    """Parágrafo maior que o máximo: quebra por frases."""
    if len(paragrafo) <= maximo:
        return [paragrafo]
    partes, atual = [], ""
    for frase in re.split(r"(?<=[.!?;])\s+", paragrafo):
        if atual and len(atual) + len(frase) + 1 > maximo:
            partes.append(atual)
            atual = frase
        else:
            atual = f"{atual} {frase}".strip()
    if atual:
        partes.append(atual)
    return partes


def _cauda(texto, tamanho):
    """Os últimos ~tamanho caracteres, começando numa palavra inteira (a sobreposição)."""
    if len(texto) <= tamanho:
        return texto
    cauda = texto[-tamanho:]
    espaco = cauda.find(" ")
    return cauda[espaco + 1:] if espaco >= 0 else cauda


def dividir_documento(titulo, texto, maximo=MAX_TRECHO, sobreposicao=SOBREPOSICAO):
    """Divide um documento em trechos. Primeiro por seção (## Título); se a seção for grande, por parágrafo,
    repetindo o fim do trecho anterior no começo do próximo (sobreposição) para não cortar uma ideia no meio.
    Cada trecho começa com 'Documento › Seção', para o vetor não perder o contexto."""
    texto = re.sub(r"\r\n?", "\n", texto or "").strip()
    trechos = []
    for secao, corpo in _secoes(texto) or [("", texto)]:
        cabecalho = f"{titulo} › {secao}" if secao else titulo
        paragrafos = [p.strip() for p in re.split(r"\n\s*\n", corpo) if p.strip()]
        pedacos = [parte for p in paragrafos for parte in _partes_pequenas(p, maximo)]
        atual = ""
        for pedaco in pedacos:
            if atual and len(atual) + len(pedaco) + 2 > maximo:
                trechos.append({"secao": secao, "conteudo": f"{cabecalho}\n{atual}"})
                atual = f"{_cauda(atual, sobreposicao)}\n\n{pedaco}"
            else:
                atual = f"{atual}\n\n{pedaco}".strip()
        if atual:
            trechos.append({"secao": secao, "conteudo": f"{cabecalho}\n{atual}"})
    return trechos


def marcar_sobreposicao(titulo, texto):
    """Os trechos do documento com a parte repetida do trecho anterior separada (o painel mostra destacada)."""
    saida, anterior = [], None
    for t in dividir_documento(titulo, texto):
        cabecalho, _, corpo = t["conteudo"].partition("\n")
        repetido = ""
        if anterior and anterior["secao"] == t["secao"]:
            cauda = _cauda(anterior["corpo"], SOBREPOSICAO)
            if corpo.startswith(f"{cauda}\n\n"):
                repetido = cauda
        saida.append({"secao": t["secao"], "cabecalho": cabecalho, "repetido": repetido,
                      "texto": corpo[len(repetido):].strip(), "caracteres": len(t["conteudo"])})
        anterior = {"secao": t["secao"], "corpo": corpo}
    return saida


def texto_de_pdf(conteudo):
    """Extrai o texto de um PDF (bytes)."""
    from io import BytesIO

    from pypdf import PdfReader
    leitor = PdfReader(BytesIO(conteudo))
    paginas = [(pagina.extract_text() or "").strip() for pagina in leitor.pages]
    texto = "\n\n".join(p for p in paginas if p)
    texto = re.sub(r"[ \t]+", " ", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()
