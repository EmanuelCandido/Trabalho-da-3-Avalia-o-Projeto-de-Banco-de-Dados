"""Testes dos filtros tirados da pergunta e da leitura das citações (rodar: python -m pytest testes)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ia import busca, rag  # noqa: E402


def test_preco_maximo():
    assert busca.extrair_filtros("presente até R$ 200")["preco_max"] == 200
    assert busca.extrair_filtros("algo até 150 reais")["preco_max"] == 150
    assert busca.extrair_filtros("camiseta por no máximo 99,90")["preco_max"] == 99.9
    assert busca.extrair_filtros("bolsa abaixo de 300")["preco_max"] == 300


def test_preco_minimo():
    assert busca.extrair_filtros("peças acima de R$ 300")["preco_min"] == 300


def test_numeros_que_nao_sao_preco():
    assert "preco_max" not in busca.extrair_filtros("posso trocar até 30 dias depois?")
    assert "preco_max" not in busca.extrair_filtros("tenho até 94 cm de busto")
    assert "preco_max" not in busca.extrair_filtros("dá para parcelar em até 3 vezes?")
    assert "preco_max" not in busca.extrair_filtros("frete grátis a partir de quanto?")


def test_genero():
    assert busca.extrair_filtros("presente para o meu pai")["genero"] == "Masculino"
    assert busca.extrair_filtros("blusa feminina")["genero"] == "Feminino"
    assert busca.extrair_filtros("presente pra minha mãe")["genero"] == "Feminino"
    assert "genero" not in busca.extrair_filtros("roupa masculina ou feminina")
    assert "genero" not in busca.extrair_filtros("algo fresco para o calor")


def test_descarte_por_filtro():
    polo = {"preco_final": 239.0, "genero": "Masculino"}
    cinto = {"preco_final": 149.0, "genero": "Unissex"}
    assert busca._motivo_descarte(polo, {"preco_max": 200})
    assert busca._motivo_descarte(cinto, {"preco_max": 200, "genero": "Masculino"}) is None
    assert busca._motivo_descarte(polo, {"genero": "Feminino"})


def test_citacoes_invalidas_saem_do_texto():
    texto, usados = rag._citacoes("A troca é em 30 dias [1]. Frete grátis [7]. Veja também [2, 9].", total=3)
    assert texto == "A troca é em 30 dias [1]. Frete grátis. Veja também [2]."
    assert usados == [1, 2]


def test_consulta_so_reescreve_pergunta_curta_numa_conversa(monkeypatch):
    chamadas = []
    monkeypatch.setattr(rag, "_reescrever", lambda p, h: chamadas.append(p) or "Quais os tamanhos da camisa de linho?")
    historico = [{"papel": "usuario", "texto": "Tem camisa de linho?"}, {"papel": "modelo", "texto": "Tem [1]."}]
    assert rag._consulta("e em quais tamanhos?", historico, None) == "Quais os tamanhos da camisa de linho?"
    longa = "quero uma bolsa de couro para usar no trabalho e também nos fins de semana com amigos"
    assert rag._consulta(longa, historico, None) == longa          # longa: já é independente
    assert rag._consulta("tem camisa de linho?", [], None) == "tem camisa de linho?"  # sem conversa
    assert chamadas == ["e em quais tamanhos?"]


def test_consulta_na_pagina_do_produto_leva_o_nome():
    produto = {"nome": "Vestido Midi de Linho"}
    assert rag._consulta("ela amassa?", [], produto) == "Vestido Midi de Linho: ela amassa?"


def test_corte_da_pagina_de_busca():
    # nada parecido o bastante (ex.: "tênis"): nenhum resultado
    assert busca._corte([0.615, 0.614, 0.606, 0.59], tem_filtro=False) is None
    assert busca._corte([], tem_filtro=False) is None
    # uma peça se destaca: só ela passa do corte
    peca_so = [0.694, 0.616, 0.613, 0.602, 0.602, 0.598, 0.595, 0.59]
    corte = busca._corte(peca_so, tem_filtro=False)
    assert [s for s in peca_so if s >= corte] == [0.694]
    # o corte nunca fica abaixo do limiar
    assert busca._corte([0.65, 0.40, 0.40, 0.40], tem_filtro=False) >= busca.LIMIAR
    # a própria busca já estreita ("masculino até R$ 200"): vale só o limiar
    assert busca._corte([0.663, 0.65, 0.633, 0.62], tem_filtro=True) == busca.LIMIAR


def test_sobreposicao_dos_trechos():
    from ia import textos
    corpo = "\n\n".join(f"Parágrafo {i}: " + "texto de teste com várias palavras. " * 12 for i in range(5))
    trechos = textos.marcar_sobreposicao("Doc", f"# Doc\n\n## Seção\n\n{corpo}\n\n## Outra\n\nFim do documento.")
    assert trechos[0]["repetido"] == ""
    assert all(t["repetido"] for t in trechos[1:] if t["secao"] == "Seção")
    assert trechos[-1] == {**trechos[-1], "secao": "Outra", "repetido": ""}  # seção nova não repete a anterior
    assert all(len(t["repetido"]) <= textos.SOBREPOSICAO for t in trechos)


def test_arquivos_recusados():
    import pytest
    import admin_ia
    for nome, conteudo in [("a.exe", b"abc"), ("a.txt", b""), ("a.pdf", b"nao e pdf"), ("a.txt", b"a\x00b")]:
        with pytest.raises(admin_ia._ArquivoInvalido):
            admin_ia._texto_do_arquivo(nome, conteudo)
    assert admin_ia._texto_do_arquivo("a.txt", "Atenção".encode("cp1252")) == "Atenção"
