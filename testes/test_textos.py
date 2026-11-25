"""Testes da montagem de textos e da divisão em trechos (rodar: python -m pytest testes)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ia import gemini, textos  # noqa: E402


def test_faixa_de_preco():
    assert textos.faixa_preco(149) == "até R$ 150"
    assert textos.faixa_preco(150) == "de R$ 150 a R$ 300"
    assert textos.faixa_preco(499.9) == "de R$ 300 a R$ 500"
    assert textos.faixa_preco(800) == "acima de R$ 500"


def test_secao_pequena_vira_um_trecho_com_cabecalho():
    trechos = textos.dividir_documento("Políticas", "# Políticas\n\n## Trocas\n\nAté 30 dias.\n\n## Frete\n\nGrátis.")
    assert [t["secao"] for t in trechos] == ["Trocas", "Frete"]
    assert trechos[0]["conteudo"] == "Políticas › Trocas\nAté 30 dias."


def test_secao_grande_divide_com_sobreposicao():
    paragrafos = [f"Parágrafo {i} " + "palavra " * 40 for i in range(6)]
    texto = "## Longa\n\n" + "\n\n".join(paragrafos)
    trechos = textos.dividir_documento("Doc", texto, maximo=600, sobreposicao=120)
    assert len(trechos) > 1
    for t in trechos:
        assert t["conteudo"].startswith("Doc › Longa\n")
        assert len(t["conteudo"]) <= 600 + 120 + len("Doc › Longa\n") + 2
    # o começo de cada trecho repete o fim do anterior
    for anterior, proximo in zip(trechos, trechos[1:]):
        corpo_proximo = proximo["conteudo"].split("\n", 1)[1]
        repetido = corpo_proximo.split("\n\n")[0]
        assert repetido and repetido in anterior["conteudo"]


def test_texto_sem_titulos_vira_uma_secao():
    trechos = textos.dividir_documento("Upload", "Primeiro parágrafo.\n\nSegundo parágrafo.")
    assert len(trechos) == 1 and trechos[0]["conteudo"].startswith("Upload\n")


def test_produto_sem_preco_nem_estoque_no_texto():
    p = {"nome": "Camisa", "categoria": "Roupas", "genero": "Feminino", "material": "Linho", "composicao": "100% linho.",
         "cores": [{"nome": "Branco", "hex": "#fff"}], "tamanhos": ["P", "M"], "preco_final": 289.0, "estoque": 7,
         "destaques": {"novidade": True}, "descricao": "Fresca.", "atributos": {"Gola": "Padre"}}
    texto = textos.texto_produto(p)
    assert "289" not in texto and "estoque" not in texto.lower()
    assert "Faixa de preço: de R$ 150 a R$ 300." in texto
    assert "Tamanhos: P e M." in texto


def test_avaliacoes_respeitam_o_limite():
    avaliacoes = [{"nome": f"Cliente {i}", "nota": 5, "titulo": "Bom", "texto": "x" * 300} for i in range(10)]
    texto = textos.texto_avaliacoes({"nome": "Polo", "nota_media": 5.0, "avaliacoes": avaliacoes})
    assert len(texto) <= textos.MAX_AVALIACOES
    assert textos.texto_avaliacoes({"nome": "Polo", "avaliacoes": []}) is None


def test_vetor_normalizado_tem_tamanho_1():
    v = gemini.normalizar([3.0, 4.0])
    assert abs(sum(x * x for x in v) - 1) < 1e-9
