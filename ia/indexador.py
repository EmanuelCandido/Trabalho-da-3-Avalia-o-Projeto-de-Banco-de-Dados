"""Mantém a tabela conhecimento (pgvector) em dia com o MongoDB e com os documentos da base.

Fluxo de cada sincronização:
  1. monta os textos (ia/textos.py) e calcula o hash de cada um;
  2. compara com o hash e o modelo já gravados: o que não mudou não gasta cota da API;
  3. gera os embeddings só do que mudou (Gemini, RETRIEVAL_DOCUMENT) e faz upsert;
  4. apaga os trechos que sobraram (produto desativado ou excluído, seção removida de um documento);
  5. registra tudo na tabela indexacoes.
"""
import time
from pathlib import Path

import requests

from bancos import mongo, vetorial
from ia import gemini, textos

PASTA = Path(__file__).resolve().parent.parent / "conhecimento"
FONTES_PRODUTO = ("produto", "avaliacao")

_n8n = {"url": "", "segredo": ""}


def init(n8n_url="", n8n_segredo=""):
    _n8n.update(url=n8n_url or "", segredo=n8n_segredo or "")


def _chave(t):
    return (t["fonte"], t["referencia"], t["trecho"])


# ---------------------------------------------------------------- textos de cada fonte

def trechos_do_produto(p):
    """Trechos de um produto serializado (completo=True). Produto inativo ou inexistente: nenhum."""
    if not p or not p.get("ativo"):
        return []
    texto = textos.texto_produto(p)
    meta = textos.metadados_produto(p)
    trechos = [{"fonte": "produto", "referencia": p["id"], "trecho": 0, "titulo": p["nome"],
                "conteudo": texto, "metadados": meta, "hash": textos.hash_texto(texto)}]
    avaliacoes = textos.texto_avaliacoes(p)
    if avaliacoes:
        trechos.append({"fonte": "avaliacao", "referencia": p["id"], "trecho": 0,
                        "titulo": f"Avaliações: {p['nome']}", "conteudo": avaliacoes,
                        "metadados": {**meta, "total": p.get("total_avaliacoes"), "nota": p.get("nota_media")},
                        "hash": textos.hash_texto(avaliacoes)})
    return trechos


def trechos_do_documento(doc):
    if not doc or not doc.get("ativo", True):
        return []
    trechos = []
    for i, parte in enumerate(textos.dividir_documento(doc["titulo"], doc["texto"])):
        trechos.append({
            "fonte": "documento", "referencia": str(doc["id"]), "trecho": i,
            "titulo": f"{doc['titulo']} › {parte['secao']}" if parte["secao"] else doc["titulo"],
            "conteudo": parte["conteudo"],
            "metadados": {"documento": doc["titulo"], "secao": parte["secao"], "origem": doc["origem"]},
            "hash": textos.hash_texto(parte["conteudo"]),
        })
    return trechos


def produtos_ativos():
    return [mongo.serializar(d, completo=True) for d in mongo.produtos().find({"ativo": True})]


def pendencias():
    """O que está diferente entre a origem (MongoDB e documentos) e o índice, sem chamar a API:
    {'mudou': trechos novos ou alterados, 'sobrando': trechos de itens que não existem mais}."""
    trechos = [t for p in produtos_ativos() for t in trechos_do_produto(p)]
    trechos += [t for d in vetorial.listar_documentos(so_ativos=True) for t in trechos_do_documento(d)]
    atuais = vetorial.hashes((*FONTES_PRODUTO, "documento"))
    modelo, chaves = gemini.modelo_embedding(), {_chave(t) for t in trechos}
    return {"mudou": sum(1 for t in trechos if atuais.get(_chave(t)) != (t["hash"], modelo)),
            "sobrando": sum(1 for k in atuais if k not in chaves)}


# ---------------------------------------------------------------- sincronização

def _sincronizar(trechos, fontes, referencias, origem, escopo):
    """referencias=None compara com TODAS as linhas dessas fontes (assim as órfãs também são apagadas)."""
    inicio = time.perf_counter()
    modelo = gemini.modelo_embedding()
    try:
        atuais = vetorial.hashes(fontes, referencias)
        novos = [t for t in trechos if atuais.get(_chave(t)) != (t["hash"], modelo)]
        chaves = {_chave(t) for t in trechos}
        sobrando = [k for k in atuais if k not in chaves]
        if novos:
            vetores = gemini.embeddings([t["conteudo"] for t in novos], "RETRIEVAL_DOCUMENT",
                                        [t["titulo"] for t in novos])
            for t, vetor in zip(novos, vetores):
                t.update(embedding=vetor, modelo=modelo)
            vetorial.gravar_trechos(novos)
        removidos = vetorial.remover_chaves(sobrando) if sobrando else 0
    except Exception as erro:
        vetorial.registrar_indexacao(origem, escopo, ms=round((time.perf_counter() - inicio) * 1000),
                                     status="erro", erro=str(erro))
        raise
    resultado = {"novos": len(novos), "iguais": len(trechos) - len(novos), "removidos": removidos,
                 "ms": round((time.perf_counter() - inicio) * 1000)}
    vetorial.registrar_indexacao(origem, escopo, resultado["novos"], resultado["iguais"], removidos, resultado["ms"])
    return resultado


def indexar_produto(produto_id, origem="automatica"):
    produto_id = str(produto_id)
    p = mongo.por_id(produto_id, completo=True)
    return _sincronizar(trechos_do_produto(p), FONTES_PRODUTO, [produto_id], origem, f"produto:{produto_id}")


def indexar_catalogo(origem="script"):
    trechos = [t for p in produtos_ativos() for t in trechos_do_produto(p)]
    return _sincronizar(trechos, FONTES_PRODUTO, None, origem, "catalogo")


def importar_pasta():
    """Copia os .md de conhecimento/ para a tabela documentos (cria ou atualiza pelo nome do arquivo)."""
    importados = []
    for arquivo in sorted(PASTA.glob("*.md")):
        texto = arquivo.read_text(encoding="utf-8")
        titulo = textos.titulo_markdown(texto, arquivo.stem.replace("-", " ").capitalize())
        vetorial.salvar_documento(titulo, f"conhecimento/{arquivo.name}", texto)
        importados.append(titulo)
    return importados


def indexar_documentos(origem="script", documento_id=None):
    if documento_id:
        docs = [vetorial.documento(documento_id)]
        referencias = [str(documento_id)]
    else:
        docs = vetorial.listar_documentos(so_ativos=True)
        referencias = None
    trechos_por_doc = {str(d["id"]): trechos_do_documento(d) for d in docs if d}
    trechos = [t for lista in trechos_por_doc.values() for t in lista]
    resultado = _sincronizar(trechos, ("documento",), referencias, origem,
                             f"documento:{documento_id}" if documento_id else "documentos")
    for doc_id, lista in trechos_por_doc.items():
        vetorial.definir_trechos_documento(doc_id, len(lista))
    return resultado


def indexar_tudo(origem="script"):
    importar_pasta()
    catalogo = indexar_catalogo(origem)
    documentos = indexar_documentos(origem)
    return {chave: catalogo[chave] + documentos[chave] for chave in ("novos", "iguais", "removidos", "ms")}


# ---------------------------------------------------------------- chamado pelo painel ao salvar um produto

def agendar(produto_id):
    """Pede ao n8n para indexar o produto; se o n8n não estiver configurado ou não responder em 2,5 s,
    o próprio Python indexa (na Vercel não dá para deixar tarefa rodando depois da resposta).
    Devolve quem indexou: 'n8n', 'python' ou None (IA desligada ou erro)."""
    if _n8n["url"]:
        try:
            r = requests.post(_n8n["url"], json={"produto_id": str(produto_id)}, timeout=2.5,
                              headers={"X-NOMA-Segredo": _n8n["segredo"]})
            if r.ok:
                return "n8n"
        except requests.RequestException:
            pass
    if not gemini.ativo():
        return None
    try:
        indexar_produto(produto_id, origem="automatica")
        return "python"
    except Exception:
        return None
