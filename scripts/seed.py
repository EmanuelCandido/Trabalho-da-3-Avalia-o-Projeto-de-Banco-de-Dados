"""Popula o MongoDB com os produtos da NOMA (fotos geradas com IA em static/img/produtos).

Uso:
    python scripts/seed.py            # insere ou atualiza pelos slugs (não apaga o que o admin cadastrou)
    python scripts/seed.py --limpar   # apaga todos os produtos antes
"""
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bancos import mongo, redis_store  # noqa: E402
from config import Config  # noqa: E402

IMG = "/static/img/produtos/"
ROUPA = ["P", "M", "G", "GG", "XGG"]
ROUPA_F = ["PP", "P", "M", "G", "GG"]
PRETO = {"nome": "Preto", "hex": "#151515"}

PRODUTOS = [
    dict(nome="Camiseta Masculina Essencial", categoria="Roupas", genero="Masculino", preco=189, promo=132,
         vendidos=1240, estoque=40, cores=[PRETO, {"nome": "Branco", "hex": "#f4f3ef"}], tamanhos=ROUPA,
         material="Algodão", composicao="100% algodão penteado. Lavar à mão ou na máquina em água fria; não usar alvejante.",
         imagens=["camiseta-masculina-essencial"], destaques=["oferta"],
         descricao="A camiseta que vai com tudo. Malha de algodão penteado com toque macio, gola careca reforçada que não deforma e caimento reto na medida certa: nem justa, nem larga. Feita para o uso diário, da reunião ao fim de semana.",
         atributos={"Gola": "Careca", "Manga": "Curta", "Caimento": "Regular", "Gramatura": "160 g/m²"}),
    dict(nome="Camiseta Feminina Essencial", categoria="Roupas", genero="Feminino", preco=179, promo=125,
         vendidos=986, estoque=34, cores=[PRETO], tamanhos=ROUPA_F, material="Algodão",
         composicao="96% algodão, 4% elastano. Lavar em água fria e secar à sombra.",
         imagens=["camiseta-feminina-essencial"], destaques=["oferta"],
         descricao="Modelagem levemente acinturada, com elastano para acompanhar o movimento. A malha encorpada não fica transparente e mantém a cor lavagem após lavagem.",
         atributos={"Gola": "Careca", "Manga": "Curta", "Caimento": "Ajustado", "Toque": "Macio e encorpado"}),
    dict(nome="Blusa Cropped Feminina Leve", categoria="Roupas", genero="Feminino", preco=129, promo=90,
         vendidos=453, estoque=22, cores=[{"nome": "Branco", "hex": "#f4f3ef"}, PRETO], tamanhos=["PP", "P", "M", "G"],
         material="Algodão", composicao="100% algodão. Lavar do avesso em água fria.",
         imagens=["blusa-cropped-feminina-leve"], destaques=["oferta"],
         descricao="Cropped de algodão leve, com comprimento pensado para cintura alta. Fresca para os dias quentes e fácil de combinar com jeans, saias e alfaiataria.",
         atributos={"Comprimento": "Cropped", "Manga": "Curta", "Estilo": "Casual"}),
    dict(nome="Camisa Polo Masculina Clássica", categoria="Roupas", genero="Masculino", preco=299, promo=239,
         vendidos=672, estoque=18, cores=[{"nome": "Dust Beige", "hex": "#b8a7a2"}, {"nome": "Branco", "hex": "#f4f3ef"}],
         tamanhos=ROUPA, material="Algodão",
         composicao="94% algodão, 6% elastano. Estampa interna com grafeno. Lavar à máquina em ciclo delicado.",
         imagens=["polo-1", "polo-2", "polo-3", "polo-4", "camisa-polo-branca"], destaques=["oferta"],
         descricao="Camisa polo desenvolvida para quem busca conforto térmico no dia a dia sem abrir mão de um visual sofisticado. Ideal para rotinas híbridas, do trabalho ao esporte e ao lazer. Com tecido mais encorpado, que marca menos o corpo, e tecnologia de grafeno aplicada na estampa interna, que distribui o calor de forma homogênea e favorece a troca térmica entre o corpo e o ambiente.",
         atributos={"Gola": "Polo com 3 botões", "Caimento": "Regular", "Tecnologia": "Controle térmico com grafeno",
                    "Origem": "Fabricada no Brasil"},
         avaliacoes=[("André L.", 5, "Ótimo caimento", "Tecido leve e confortável. A polo veste bem e funciona tanto no trabalho quanto no fim de semana.", "M", "Dust Beige"),
                     ("Rafael M.", 5, "Acabamento muito bom", "Gostei do toque do tecido e dos detalhes. A peça manteve a forma depois da lavagem.", "G", "Dust Beige"),
                     ("Bruno S.", 4, "Boa para o dia a dia", "A modelagem é bonita e a cor combina com tudo. Segui o guia de medidas e o tamanho deu certo.", "M", "Dust Beige")]),
    dict(nome="Kit 3 Regatas Femininas Brisa", categoria="Roupas", genero="Feminino", preco=447, promo=335,
         vendidos=815, estoque=15, cores=[{"nome": "Preto e marinho", "hex": "#1f2a44"}], tamanhos=ROUPA_F,
         material="Viscose", composicao="95% viscose, 5% elastano. Kit com 3 peças (2 pretas e 1 azul-marinho).",
         imagens=["kit-3-regatas-femininas-brisa"], destaques=["oferta"],
         descricao="Três regatas de alças finas e reguláveis, em viscose fluida que não marca. A base perfeita para sobreposições ou para usar sozinha nos dias quentes.",
         atributos={"Peças no kit": "3", "Alças": "Finas e reguláveis", "Decote": "Reto"}),
    dict(nome="Kit 3 Camisetas Masculinas Essenciais", categoria="Roupas", genero="Masculino", preco=567, promo=340,
         vendidos=1530, estoque=26, cores=[{"nome": "Preto, branco e chumbo", "hex": "#4a4d50"}], tamanhos=ROUPA,
         material="Algodão", composicao="100% algodão penteado. Kit com 3 peças: preta, branca e chumbo.",
         imagens=["kit-3-camisetas-masculinas-essenciais"], destaques=["oferta"],
         descricao="O trio que resolve a semana. Três camisetas de algodão penteado nas cores mais versáteis do guarda-roupa, com o mesmo caimento da nossa Camiseta Essencial.",
         atributos={"Peças no kit": "3", "Gola": "Careca", "Caimento": "Regular"}),
    dict(nome="Short Esportivo Masculino Impulso", categoria="Roupas", genero="Masculino", preco=289, promo=173,
         vendidos=394, estoque=0, cores=[PRETO], tamanhos=["P", "M", "G", "GG"], material="Poliamida",
         composicao="88% poliamida, 12% elastano. Secagem rápida. Não passar.",
         imagens=["short-esportivo-masculino-impulso"], destaques=["oferta"],
         descricao="Short leve de secagem rápida, com cós elástico, cordão interno e bolso traseiro com zíper para a chave. Feito para correr, treinar e o que vier depois.",
         atributos={"Comprimento": "Acima do joelho", "Bolsos": "2 laterais + 1 traseiro com zíper",
                    "Indicação": "Corrida e treino"}),
    dict(nome="Saia Longa Feminina Movimento", categoria="Roupas", genero="Feminino", preco=429, promo=322,
         vendidos=268, estoque=12, cores=[{"nome": "Verde Oliva", "hex": "#5d5b35"}], tamanhos=["PP", "P", "M", "G"],
         material="Viscose", composicao="100% viscose. Lavar à mão em água fria.",
         imagens=["saia-longa-feminina-movimento"], destaques=["oferta"],
         descricao="Saia longa e fluida, com cós de elástico embutido e caimento que acompanha cada passo. Funciona com tênis no dia a dia e com sandália à noite.",
         atributos={"Comprimento": "Longo (até o tornozelo)", "Cós": "Elástico embutido", "Forro": "Sim"}),
    dict(nome="Cinto de couro", categoria="Acessórios", genero="Unissex", preco=149, promo=None, vendidos=187,
         estoque=30, cores=[{"nome": "Caramelo", "hex": "#a4622d"}], tamanhos=["Único"], material="Couro",
         composicao="Couro bovino legítimo; fivela de metal escovado.",
         imagens=["cinto-de-couro"], destaques=[],
         descricao="Cinto de couro legítimo com costura aparente e fivela em metal escovado dourado. Um clássico que melhora com o tempo.",
         atributos={"Largura": "3,5 cm", "Fivela": "Metal escovado", "Ajuste": "5 furos"}),
    dict(nome="Óculos solar Duna", categoria="Acessórios", genero="Unissex", preco=199, promo=None, vendidos=231,
         estoque=20, cores=[{"nome": "Tartaruga", "hex": "#c9a15a"}], tamanhos=["Único"], material="Acetato",
         composicao="Armação em acetato; lentes de policarbonato com proteção UV400.",
         imagens=["oculos-solar-duna"], destaques=[],
         descricao="Armação arredondada em acetato tartaruga e lentes marrons que suavizam a luz sem distorcer as cores. Acompanha estojo e flanela.",
         atributos={"Lentes": "Marrom, polarizadas", "Proteção": "UV400", "Formato": "Arredondado"}),
    dict(nome="Bolsa meia-lua", categoria="Acessórios", genero="Feminino", preco=349, promo=None, vendidos=156,
         estoque=9, cores=[{"nome": "Café", "hex": "#9c6b43"}], tamanhos=["Único"], material="Couro",
         composicao="Couro bovino; forro em algodão; ferragens em metal.",
         imagens=["bolsa-meia-lua"], destaques=[],
         descricao="Bolsa de ombro em formato meia-lua, em couro macio com acabamento fosco. Cabe o essencial: celular, carteira, chaves e óculos.",
         atributos={"Dimensões": "32 × 18 × 7 cm", "Fechamento": "Zíper", "Alça": "Fixa, de ombro"}),
    dict(nome="Blusa Gola Alta Feminina Essencial", categoria="Roupas", genero="Feminino", preco=259, promo=181,
         vendidos=512, estoque=17, cores=[PRETO], tamanhos=ROUPA_F, material="Viscose",
         composicao="92% viscose, 8% elastano. Lavar do avesso.",
         imagens=["blusa-gola-alta-feminina-essencial"], destaques=["queridinho"],
         descricao="Gola alta, manga longa e malha canelada com elastano: a segunda pele que funciona sozinha ou por baixo de camisas e blazers.",
         atributos={"Gola": "Alta", "Manga": "Longa", "Malha": "Canelada"}),
    dict(nome="Calça reta de alfaiataria", categoria="Roupas", genero="Feminino", preco=329, promo=None,
         vendidos=512, estoque=14, cores=[{"nome": "Chumbo", "hex": "#2b2b2d"}], tamanhos=ROUPA_F,
         material="Alfaiataria", composicao="64% poliéster, 33% viscose, 3% elastano. Passar em temperatura média.",
         imagens=["calca-reta-de-alfaiataria"], destaques=["queridinho"],
         descricao="Calça de cintura alta com vinco marcado e perna reta. O tecido de alfaiataria com elastano não amassa e dá conforto o dia inteiro.",
         atributos={"Cintura": "Alta", "Modelagem": "Reta", "Bolsos": "2 faca + 2 traseiros embutidos"}),
    dict(nome="Camisa de linho", categoria="Roupas", genero="Feminino", preco=289, promo=None, vendidos=309,
         estoque=16, cores=[{"nome": "Areia", "hex": "#e3d8c8"}], tamanhos=ROUPA_F, material="Linho",
         composicao="100% linho. Lavar à mão; o amassado natural faz parte do charme.",
         imagens=["camisa-de-linho"], destaques=["queridinho"],
         descricao="Camisa de linho puro, leve e respirável, com modelagem um pouco mais solta e barra arredondada. Por dentro ou por fora da calça.",
         atributos={"Gola": "Clássica", "Manga": "Longa com punho", "Caimento": "Amplo"}),
    dict(nome="Tricô de algodão", categoria="Roupas", genero="Unissex", preco=259, promo=None, vendidos=512,
         estoque=21, cores=[{"nome": "Verde Oliva", "hex": "#5c6b3a"}], tamanhos=["P", "M", "G", "GG"],
         material="Algodão", composicao="100% algodão. Secar na horizontal.",
         imagens=["trico-de-algodao"], destaques=[],
         descricao="Suéter de tricô em algodão, com ponto fechado e punhos canelados. Aquece sem pesar nas noites de meia-estação.",
         atributos={"Gola": "Careca", "Ponto": "Jersey", "Peso": "Médio"}),
    dict(nome="Vestido Midi de Linho", categoria="Roupas", genero="Feminino", preco=389, promo=None, vendidos=74,
         estoque=11, cores=[{"nome": "Off-white", "hex": "#efe9dc"}], tamanhos=["PP", "P", "M", "G"], material="Linho",
         composicao="55% linho, 45% viscose. Lavar à mão.",
         imagens=["vestido-midi-linho"], destaques=["novidade"],
         descricao="Vestido midi de alças largas, em linho com viscose para um caimento mais fluido. Fresco, elegante e com bolsos laterais.",
         atributos={"Comprimento": "Midi", "Alças": "Largas", "Bolsos": "Laterais"}),
    dict(nome="Jaqueta de Sarja Masculina", categoria="Roupas", genero="Masculino", preco=459, promo=None,
         vendidos=58, estoque=8, cores=[{"nome": "Cáqui", "hex": "#8a7a52"}], tamanhos=["P", "M", "G", "GG"],
         material="Sarja", composicao="100% algodão (sarja). Lavar do avesso.",
         imagens=["jaqueta-sarja-masculina"], destaques=["novidade"],
         descricao="Jaqueta de sarja de algodão com bolsos de chapa e botões de metal. A terceira peça que transforma o look básico.",
         atributos={"Fechamento": "Botões de metal", "Bolsos": "4", "Forro": "Não"}),
    dict(nome="Boné de Algodão", categoria="Acessórios", genero="Unissex", preco=119, promo=None, vendidos=96,
         estoque=25, cores=[{"nome": "Areia", "hex": "#cdbb98"}], tamanhos=["Único"], material="Algodão",
         composicao="100% algodão (sarja lavada). Ajuste traseiro com fivela.",
         imagens=["bone-algodao"], destaques=["novidade"],
         descricao="Boné de seis gomos em sarja lavada, aba curva e ajuste traseiro com fivela metálica.",
         atributos={"Aba": "Curva", "Ajuste": "Fivela metálica", "Gomos": "6"}),
]

NOMES = ["Mariana C.", "Lucas P.", "Juliana R.", "Pedro H.", "Camila T.", "Thiago A.", "Larissa M.", "Gabriel S.",
         "Beatriz F.", "Felipe O."]
OPINIOES = [
    (5, "Virou favorita", "Uso toda semana. O tecido é muito bom e não desbotou."),
    (5, "Vale cada centavo", "Qualidade acima do que eu esperava pelo preço."),
    (4, "Muito bonita", "Gostei bastante. Achei a forma um pouco grande, mas ficou ótima."),
    (5, "Chegou rápido", "Chegou antes do prazo e igual às fotos."),
    (4, "Confortável", "Leve e confortável. Compraria de novo em outra cor."),
    (3, "Boa, mas...", "A peça é bonita, mas esperava um tecido um pouco mais grosso."),
]


PASTA_FOTOS = Path(__file__).resolve().parent.parent / "static" / "img" / "produtos"


def fotos(nomes):
    """Foto principal de cada nome e, se existir, a segunda foto (nome-2.jpg) logo depois."""
    lista = []
    for nome in nomes:
        lista.append(IMG + nome + ".jpg")
        if (PASTA_FOTOS / f"{nome}-2.jpg").exists():
            lista.append(IMG + nome + "-2.jpg")
    return lista


def montar(p, posicao):
    agora = datetime.now(timezone.utc)
    rnd = random.Random(p["nome"])
    if "avaliacoes" in p:
        avaliacoes = [{"nome": n, "nota": nota, "titulo": t, "texto": txt, "tamanho": tam, "cor": cor,
                       "data": agora - timedelta(days=4 * i + 2)}
                      for i, (n, nota, t, txt, tam, cor) in enumerate(p["avaliacoes"])]
    else:
        avaliacoes = []
        for i in range(rnd.randint(0, 4)):
            nota, titulo, texto = rnd.choice(OPINIOES)
            avaliacoes.append({"nome": rnd.choice(NOMES), "nota": nota, "titulo": titulo, "texto": texto,
                               "tamanho": rnd.choice(p["tamanhos"]), "cor": p["cores"][0]["nome"],
                               "data": agora - timedelta(days=rnd.randint(1, 90))})
    preco_final = p["promo"] if p["promo"] else p["preco"]
    return {
        "slug": mongo.slugify(p["nome"]), "nome": p["nome"], "descricao": p["descricao"],
        "categoria": p["categoria"], "genero": p["genero"], "preco": float(p["preco"]),
        "preco_promocional": float(p["promo"]) if p["promo"] else None, "preco_final": float(preco_final),
        "estoque": p["estoque"], "vendidos": p["vendidos"], "material": p["material"],
        "composicao": p["composicao"], "cores": p["cores"], "tamanhos": p["tamanhos"],
        "imagens": fotos(p["imagens"]),
        "destaques": {k: k in p["destaques"] for k in ("oferta", "queridinho", "novidade")},
        "atributos": p["atributos"], "avaliacoes": avaliacoes, "ativo": True, "posicao": posicao,
        # As novidades ficam com data mais recente para aparecerem primeiro na ordenação.
        "criado_em": agora - timedelta(days=1 if "novidade" in p["destaques"] else rnd.randint(20, 120)),
        "atualizado_em": agora,
    }


def main():
    mongo.init(Config.MONGO_URI, Config.MONGO_DB)
    col = mongo.produtos()
    if "--limpar" in sys.argv:
        apagados = col.delete_many({}).deleted_count
        print(f"{apagados} produto(s) apagado(s).")
    for posicao, p in enumerate(PRODUTOS, start=1):
        doc = montar(p, posicao)
        col.update_one({"slug": doc["slug"]}, {"$set": doc}, upsert=True)
        print(f"  ok  {doc['nome']}")
    print(f"{len(PRODUTOS)} produtos no MongoDB ({Config.MONGO_DB}.produtos).")
    try:
        redis_store.init(Config.REDIS_URL)
        redis_store.invalidar_cache()
        print("Cache do Redis invalidado.")
    except Exception as erro:
        print(f"Aviso: não foi possível limpar o cache do Redis ({erro}).")


if __name__ == "__main__":
    main()
