# Avaliação da recuperação (RAG)

Gerado em 25/11/2026 19:50 por `scripts/avaliar_rag.py` com 39 perguntas de `testes/perguntas.json` (33 sobre a loja e 6 fora do assunto). Modelo de embedding: `gemini-embedding-001@768`.

## Busca vetorial

| Medida | Resultado |
|---|---|
| A fonte certa veio em 1º lugar | 31 de 33 (94%) |
| A fonte certa veio entre os 5 primeiros | 33 de 33 (100%) |
| MRR (média de 1/posição do acerto) | 0.97 |

## Por grupo de pergunta

| Grupo | Perguntas | 1º lugar | Top 5 |
|---|---|---|---|
| Necessidade | 8 | 7 | 8 |
| Atributo | 6 | 6 | 6 |
| Avaliações | 4 | 4 | 4 |
| Políticas | 8 | 8 | 8 |
| Tamanhos | 3 | 2 | 3 |
| Cuidados | 2 | 2 | 2 |
| Loja | 2 | 2 | 2 |

## Busca por texto × busca vetorial (18 perguntas sobre produtos)

| Busca | Acertou entre os 5 primeiros |
|---|---|
| Regex no MongoDB (busca atual do site) | 0 de 18 |
| Índice de texto do MongoDB (`$text`, palavras-chave) | 17 de 18 |
| Vetorial (pgvector + Gemini) | 18 de 18 |

## Página /busca (18 perguntas sobre produtos)

A página mostra o que tem o termo escrito e, depois, os produtos que se destacam da média dos candidatos (`ia/busca.py`, `_corte`: o melhor precisa passar de 0,62).

| Medida | Resultado |
|---|---|
| Mostrou pelo menos uma peça esperada | 18 de 18 |
| Peças mostradas por busca (média) | 2,4 |
| Peças mostradas que estavam na lista esperada | 26 de 43 (60%) |
| Perguntas fora do assunto sem nenhuma peça | 6 de 6 |

## Limiar de similaridade

Limiar atual (`RAG_LIMIAR`): **0.60**.

| | Menor | Maior |
|---|---|---|
| Similaridade do acerto (perguntas sobre a loja) | 0.650 | 0.827 |
| Melhor similaridade (perguntas fora do assunto) | 0.490 | 0.559 |

- Perguntas da loja cujo acerto passa do limiar: 33 de 33.
- Perguntas fora do assunto barradas pelo limiar (o modelo nem é chamado): 6 de 6.
- Os dois grupos se separam: qualquer limiar entre 0.559 e 0.650 funciona. O meio do intervalo é 0.60.

## Pergunta por pergunta

| Pergunta | Posição do acerto | Similaridade | 1º resultado |
|---|---|---|---|
| algo fresco para usar no calor | 1 | 0.697 | Blusa Cropped Feminina Leve |
| roupa para os dias frios | 1 | 0.654 | Blusa Gola Alta Feminina Essencial |
| uma peça para ir ao trabalho e sair depois | 2 | 0.670 | Saia Longa Feminina Movimento |
| short para correr | 1 | 0.722 | Short Esportivo Masculino Impulso |
| bolsa pequena para sair à noite | 1 | 0.686 | Bolsa meia-lua |
| vestido leve para o verão | 1 | 0.683 | Vestido Midi de Linho |
| algo para proteger do sol | 1 | 0.697 | Óculos solar Duna |
| camisetas básicas para o dia a dia | 1 | 0.707 | Camiseta Masculina Essencial |
| qual polo tem tecnologia de grafeno? | 1 | 0.717 | Camisa Polo Masculina Clássica |
| vocês têm alguma coisa de couro? | 1 | 0.702 | Cinto de couro |
| óculos com proteção UV | 1 | 0.715 | Óculos solar Duna |
| saia longa com elástico na cintura | 1 | 0.756 | Saia Longa Feminina Movimento |
| jaqueta masculina de sarja | 1 | 0.814 | Jaqueta de Sarja Masculina |
| kit com várias regatas | 1 | 0.752 | Kit 3 Regatas Femininas Brisa |
| o que os clientes acham do caimento da polo? | 1 | 0.774 | Avaliações: Camisa Polo Masculina Clássica |
| a calça de alfaiataria tem boas avaliações? | 1 | 0.827 | Avaliações: Calça reta de alfaiataria |
| quem comprou o short gostou? | 1 | 0.731 | Avaliações: Short Esportivo Masculino Impulso |
| o vestido de linho amassa muito segundo quem comprou? | 1 | 0.717 | Avaliações: Vestido Midi de Linho |
| posso trocar depois de 20 dias? | 1 | 0.735 | Políticas da NOMA › Trocas e devoluções |
| posso devolver se me arrepender da compra? | 1 | 0.729 | Políticas da NOMA › Trocas e devoluções |
| frete grátis a partir de quanto? | 1 | 0.752 | Políticas da NOMA › Entregas e frete |
| vocês entregam no Nordeste? | 1 | 0.705 | Políticas da NOMA › Entregas e frete |
| quais as formas de pagamento? | 1 | 0.700 | Políticas da NOMA › Formas de pagamento |
| tem desconto pagando no pix? | 1 | 0.695 | Políticas da NOMA › Formas de pagamento |
| qual o horário de atendimento? | 1 | 0.731 | Políticas da NOMA › Atendimento |
| preciso criar conta para comprar? | 1 | 0.702 | Políticas da NOMA › Como comprar |
| tenho 94 cm de busto, qual tamanho eu uso? | 1 | 0.700 | Guia de tamanhos da NOMA › Tabela de medidas |
| como tirar as minhas medidas? | 1 | 0.704 | Guia de tamanhos da NOMA › Como medir |
| estou entre o M e o G, qual escolho? | 2 | 0.650 | Guia de tamanhos da NOMA › Tabela de medidas |
| como lavar roupa de linho? | 1 | 0.739 | Cuidados com as peças › Linho |
| como cuidar do cinto de couro? | 1 | 0.722 | Cuidados com as peças › Couro |
| vocês vendem tênis? | 1 | 0.683 | Sobre a NOMA › O que vendemos |
| as roupas são feitas no Brasil? | 1 | 0.692 | Sobre a NOMA › Como produzimos |
| quem ganhou a Copa do Mundo? (fora do assunto) | — | 0.492 | Short Esportivo Masculino Impulso |
| receita de bolo de chocolate (fora do assunto) | — | 0.558 | Camiseta Feminina Essencial |
| qual a capital da França? (fora do assunto) | — | 0.490 | Políticas da NOMA › Entregas e frete |
| me ajuda a resolver uma equação de segundo grau (fora do assunto) | — | 0.548 | Bolsa meia-lua |
| qual a previsão do tempo para amanhã? (fora do assunto) | — | 0.559 | Guia de tamanhos da NOMA › Entre dois tamanhos |
| como faço para trocar o óleo do carro? (fora do assunto) | — | 0.537 | Cuidados com as peças › Óculos |
