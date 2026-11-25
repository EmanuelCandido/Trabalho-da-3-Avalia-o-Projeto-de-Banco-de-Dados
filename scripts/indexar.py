"""Gera os embeddings e atualiza o banco vetorial (tabela conhecimento no Supabase).

Uso:
    python scripts/indexar.py --tudo            # catálogo do MongoDB + documentos de conhecimento/
    python scripts/indexar.py --catalogo        # só produtos e avaliações
    python scripts/indexar.py --produto <id>    # um produto (ex.: depois de editar no painel)
    python scripts/indexar.py --documentos      # só os documentos (importa a pasta conhecimento/ antes)
    python scripts/indexar.py --simular         # mostra os textos e trechos, sem chamar a API nem gravar

Só o que mudou desde a última vez gera embedding novo (comparação por hash), então rodar de novo é barato.
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from bancos import mongo, supabase  # noqa: E402
from config import Config  # noqa: E402
from ia import gemini, indexador, textos  # noqa: E402


def simular():
    produtos = indexador.produtos_ativos()
    trechos = [t for p in produtos for t in indexador.trechos_do_produto(p)]
    print(f"=== {len(produtos)} produtos ativos -> {len(trechos)} trechos "
          f"({sum(t['fonte'] == 'produto' for t in trechos)} de produto, "
          f"{sum(t['fonte'] == 'avaliacao' for t in trechos)} de avaliações)\n")
    for t in trechos[:2]:
        print(f"--- [{t['fonte']}] {t['titulo']} ({len(t['conteudo'])} caracteres)\n{t['conteudo']}\n")
    tamanhos = sorted(len(t["conteudo"]) for t in trechos)
    print(f"Tamanho dos trechos do catálogo: mínimo {tamanhos[0]}, máximo {tamanhos[-1]} caracteres.\n")

    total = 0
    for arquivo in sorted(indexador.PASTA.glob("*.md")):
        texto = arquivo.read_text(encoding="utf-8")
        titulo = textos.titulo_markdown(texto, arquivo.stem)
        partes = textos.dividir_documento(titulo, texto)
        total += len(partes)
        print(f"=== {arquivo.name}: \"{titulo}\" -> {len(partes)} trechos")
        for parte in partes:
            primeira = parte["conteudo"].splitlines()[0]
            print(f"    {len(parte['conteudo']):4d} caracteres  {primeira}")
    print(f"\nTotal: {len(trechos) + total} trechos ({len(trechos)} do catálogo + {total} de documentos).")


def mostrar(nome, r):
    print(f"{nome}: {r['novos']} novo(s) ou alterado(s), {r['iguais']} igual(is), "
          f"{r['removidos']} removido(s) em {r['ms'] / 1000:.1f} s.")


def main():
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = args.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--tudo", action="store_true")
    grupo.add_argument("--catalogo", action="store_true")
    grupo.add_argument("--produto")
    grupo.add_argument("--documentos", action="store_true")
    grupo.add_argument("--simular", action="store_true")
    opcoes = args.parse_args()

    mongo.init(Config.MONGO_URI, Config.MONGO_DB)
    if opcoes.simular:
        simular()
        return

    if not Config.GEMINI_API_KEY:
        sys.exit("Preencha GEMINI_API_KEY no .env (https://aistudio.google.com > Get API key).")
    if not Config.DATABASE_URL:
        sys.exit("Preencha DATABASE_URL no .env e rode antes: python scripts/setup_rag.py")
    supabase.init(Config.DATABASE_URL)
    supabase._pool.wait(timeout=15)
    gemini.init(Config.GEMINI_API_KEY, Config.GEMINI_MODELO, Config.GEMINI_MODELO_EMBEDDING, Config.EMBEDDING_DIM)
    print(f"Modelo de embedding: {gemini.modelo_embedding()}")

    if opcoes.tudo:
        print("Documentos importados de conhecimento/: " + ", ".join(indexador.importar_pasta()))
        mostrar("Catálogo", indexador.indexar_catalogo("script"))
        mostrar("Documentos", indexador.indexar_documentos("script"))
    elif opcoes.catalogo:
        mostrar("Catálogo", indexador.indexar_catalogo("script"))
    elif opcoes.produto:
        mostrar(f"Produto {opcoes.produto}", indexador.indexar_produto(opcoes.produto, "script"))
    elif opcoes.documentos:
        print("Documentos importados de conhecimento/: " + ", ".join(indexador.importar_pasta()))
        mostrar("Documentos", indexador.indexar_documentos("script"))


if __name__ == "__main__":
    main()
