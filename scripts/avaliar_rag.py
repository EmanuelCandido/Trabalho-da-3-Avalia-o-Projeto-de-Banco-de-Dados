"""Avalia a recuperação: a fonte certa aparece entre os primeiros resultados? E as perguntas fora do assunto ficam
abaixo do limiar? Compara a busca vetorial com as duas buscas por texto que existem no MongoDB.

Uso:
    python scripts/avaliar_rag.py             # mostra as tabelas
    python scripts/avaliar_rag.py --salvar    # também grava docs/avaliacao-rag.md (usado no README)

As perguntas e as respostas esperadas ficam em testes/perguntas.json.
Gasta 1 chamada de embedding (todas as perguntas vão num lote só).
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from bancos import mongo, supabase, vetorial  # noqa: E402
from config import Config  # noqa: E402
from ia import gemini  # noqa: E402

TOP = 5


def acertou(item, trecho):
    if item.get("fonte") and trecho["fonte"] != item["fonte"]:
        return False
    if item.get("slugs"):
        return (trecho.get("metadados") or {}).get("slug") in item["slugs"]
    return any(t.lower() in trecho["titulo"].lower() for t in item.get("titulos", []))


def busca_regex(pergunta):
    """A busca que o site usa hoje: a frase inteira como expressão regular no nome, categoria, material e cor."""
    itens, _ = mongo.listar(mongo.montar_filtro(q=pergunta), "relevancia", TOP)
    return [i["slug"] for i in itens]


def busca_texto(pergunta):
    """Índice de texto do MongoDB ($text): palavras-chave com radical em português, no nome e na descrição."""
    cursor = (mongo.produtos().find({"$text": {"$search": pergunta}, "ativo": True},
                                    {"slug": 1, "score": {"$meta": "textScore"}})
              .sort([("score", {"$meta": "textScore"})]).limit(TOP))
    return [d["slug"] for d in cursor]


def pct(valor, total):
    return f"{round(100 * valor / total)}%" if total else "—"


def main():
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--salvar", action="store_true")
    opcoes = args.parse_args()

    mongo.init(Config.MONGO_URI, Config.MONGO_DB)
    supabase.init(Config.DATABASE_URL)
    supabase._pool.wait(timeout=15)
    gemini.init(Config.GEMINI_API_KEY, Config.GEMINI_MODELO, Config.GEMINI_MODELO_EMBEDDING, Config.EMBEDDING_DIM)
    limiar = Config.RAG_LIMIAR

    itens = json.loads((RAIZ / "testes" / "perguntas.json").read_text(encoding="utf-8"))
    vetores = gemini.embeddings([i["pergunta"] for i in itens], "RETRIEVAL_QUERY")

    linhas, dentro, fora = [], [], []
    for item, vetor in zip(itens, vetores):
        resultados = vetorial.buscar(vetor, qtd=TOP)
        melhor = float(resultados[0]["similaridade"]) if resultados else 0.0
        if item.get("fora"):
            fora.append({"item": item, "melhor": melhor, "topo": resultados[0]["titulo"] if resultados else ""})
            continue
        posicao = next((n for n, r in enumerate(resultados, start=1) if acertou(item, r)), None)
        sim_acerto = float(resultados[posicao - 1]["similaridade"]) if posicao else None
        registro = {"item": item, "posicao": posicao, "sim_acerto": sim_acerto, "melhor": melhor,
                    "topo": resultados[0]["titulo"] if resultados else ""}
        if item.get("slugs"):
            registro["regex"] = any(s in item["slugs"] for s in busca_regex(item["pergunta"]))
            registro["texto"] = any(s in item["slugs"] for s in busca_texto(item["pergunta"]))
        dentro.append(registro)
        linhas.append(registro)

    n = len(dentro)
    a1 = sum(1 for r in dentro if r["posicao"] == 1)
    a5 = sum(1 for r in dentro if r["posicao"])
    mrr = sum(1 / r["posicao"] for r in dentro if r["posicao"]) / n if n else 0
    produtos = [r for r in dentro if "regex" in r]
    sims_dentro = [r["sim_acerto"] for r in dentro if r["sim_acerto"] is not None]
    sims_fora = [r["melhor"] for r in fora]
    passam = sum(1 for s in sims_dentro if s >= limiar)
    barrados = sum(1 for s in sims_fora if s < limiar)

    saida = [f"# Avaliação da recuperação (RAG)\n",
             f"Gerado em {datetime.now():%d/%m/%Y %H:%M} por `scripts/avaliar_rag.py` com "
             f"{len(itens)} perguntas de `testes/perguntas.json` "
             f"({n} sobre a loja e {len(fora)} fora do assunto). Modelo de embedding: `{gemini.modelo_embedding()}`.\n",
             "## Busca vetorial\n",
             "| Medida | Resultado |", "|---|---|",
             f"| A fonte certa veio em 1º lugar | {a1} de {n} ({pct(a1, n)}) |",
             f"| A fonte certa veio entre os {TOP} primeiros | {a5} de {n} ({pct(a5, n)}) |",
             f"| MRR (média de 1/posição do acerto) | {mrr:.2f} |", "",
             "## Por grupo de pergunta\n", "| Grupo | Perguntas | 1º lugar | Top 5 |", "|---|---|---|---|"]
    grupos = {}
    for r in dentro:
        g = grupos.setdefault(r["item"]["grupo"], [0, 0, 0])
        g[0] += 1
        g[1] += r["posicao"] == 1
        g[2] += bool(r["posicao"])
    saida += [f"| {g} | {v[0]} | {v[1]} | {v[2]} |" for g, v in grupos.items()]

    saida += ["", f"## Busca por texto × busca vetorial ({len(produtos)} perguntas sobre produtos)\n",
              "| Busca | Acertou entre os 5 primeiros |", "|---|---|",
              f"| Regex no MongoDB (busca atual do site) | {sum(r['regex'] for r in produtos)} de {len(produtos)} |",
              f"| Índice de texto do MongoDB (`$text`, palavras-chave) | {sum(r['texto'] for r in produtos)} de {len(produtos)} |",
              f"| Vetorial (pgvector + Gemini) | {sum(bool(r['posicao']) for r in produtos)} de {len(produtos)} |", ""]

    saida += ["## Limiar de similaridade\n",
              f"Limiar atual (`RAG_LIMIAR`): **{limiar:.2f}**.\n",
              "| | Menor | Maior |", "|---|---|---|",
              f"| Similaridade do acerto (perguntas sobre a loja) | {min(sims_dentro):.3f} | {max(sims_dentro):.3f} |",
              f"| Melhor similaridade (perguntas fora do assunto) | {min(sims_fora):.3f} | {max(sims_fora):.3f} |", "",
              f"- Perguntas da loja cujo acerto passa do limiar: {passam} de {len(sims_dentro)}.",
              f"- Perguntas fora do assunto barradas pelo limiar (o modelo nem é chamado): {barrados} de {len(fora)}."]
    if sims_dentro and sims_fora and min(sims_dentro) > max(sims_fora):
        sugestao = (min(sims_dentro) + max(sims_fora)) / 2
        saida.append(f"- Os dois grupos se separam: qualquer limiar entre {max(sims_fora):.3f} e {min(sims_dentro):.3f} "
                     f"funciona. O meio do intervalo é {sugestao:.2f}.")
    else:
        saida.append("- Os dois grupos se sobrepõem: nenhum limiar separa todos os casos.")

    saida += ["", "## Pergunta por pergunta\n",
              "| Pergunta | Posição do acerto | Similaridade | 1º resultado |", "|---|---|---|---|"]
    for r in dentro:
        sim = f"{r['sim_acerto']:.3f}" if r["sim_acerto"] is not None else "—"
        saida.append(f"| {r['item']['pergunta']} | {r['posicao'] or '—'} | {sim} | {r['topo']} |")
    for r in fora:
        saida.append(f"| {r['item']['pergunta']} (fora do assunto) | — | {r['melhor']:.3f} | {r['topo']} |")

    texto = "\n".join(saida) + "\n"
    print(texto)
    if opcoes.salvar:
        destino = RAIZ / "docs" / "avaliacao-rag.md"
        destino.write_text(texto, encoding="utf-8")
        print(f"Gravado em {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
