# DESIGN.md · NOMA

> Se este arquivo e o código discordarem, o código vale até a dupla decidir. Anote o conflito em Perguntas em aberto.

## Produto
Loja virtual fictícia de roupas e acessórios essenciais (trabalho de Projeto de Banco de Dados). O cliente navega pelo catálogo no celular ou no computador, monta o carrinho e finaliza pelo WhatsApp. O administrador usa o painel no computador.
Na fase do RAG, a loja ganha o chat **"Pergunte à NOMA"**, que responde dúvidas de tecido, caimento, tamanho, troca, frete e pagamento a partir do catálogo e das políticas, além da busca por significado e de "Você também pode gostar".
Trabalho principal do chat: responder em poucos segundos e levar o cliente até a peça certa.

## Público e voz
Clientes adultos que compram básicos de qualidade (suposição). Português do Brasil; dinheiro "R$ 289,00", datas "25/11/2026", horários "9h às 18h".
Voz da loja: frases curtas e diretas, simpáticas sem exagero ("Peças essenciais para combinar com a vida que acontece"). O chat vai direto ao ponto: sem "Olá!" no começo de toda resposta e sem oferecer ajuda no fim.

## Clima
Palavras: **calmo e minimalista**, **ágil e prático**.
Nunca parecer: **chatbot robótico** (mascote, avatar de robô, "Sou o assistente virtual…"), **visual "de IA"** (gradiente roxo, brilho, estrelinhas, neon), **atendimento de banco** (formal, menus e opções numeradas), **widget genérico** (bolha azul padrão de plugin de suporte).

## Marca
Sistema visual em código, feito a partir do protótipo do Figma da dupla:
- Origem do design system: `static/css/noma.css` (tokens e componentes da loja), `static/css/assistente.css` (conversa do chat, baixado no primeiro uso), `static/css/ui.css` (controles de formulário próprios), `templates/_icones.html` (ícones de linha, traço 1,75), `templates/_macros.html`. O painel usa `static/css/admin.css` no mesmo estilo.
- Cores: fundo `--fundo #f4f4f6`, superfícies brancas `--superficie`, texto `--texto #111113`, secundário `--suave #6b6b72`, linhas `--linha #e4e4e8`. Ação principal em **preto** `--preto #0b0b0c`. Azul `--azul #2463eb` só no foco do teclado. Verde `--verde-whats` só para WhatsApp. Laranja `--promo` só para promoção. Vermelho `--vermelho` só para erro.
- Tipografia: Manrope (fonte variável), corpo de 15 px; rótulos de 12 a 14 px.
- Forma: cantos `--raio 8px` e `--raio-g 14px`; sombras `--sombra` e `--sombra-g`.
- Movimento: curvas `--mola` (objetos que aparecem) e `--suavizar` (transições).
- Logo: "NOMA" em texto, peso 500 e espaçamento largo.

## Referências
- Protótipo da NOMA no Figma (feito pela dupla): pegar tudo, porque é a base de toda a loja; evitar nada.
- Busca da Apple Store: pegar o **painel limpo** (fundo claro, muito respiro, sem bordas pesadas), os **cards de produto** logo abaixo da resposta (foto pequena, nome e preço) e as **sugestões rápidas** em linhas simples para tocar; evitar **tomar a tela inteira** no computador (um painel lateral basta).

## Restrições
- Celular primeiro (375 px) e computador (1440 px).
- Só tema claro.
- Precisa funcionar em celular fraco e rede lenta: existe um "modo leve" automático (desliga desfoques e animações contínuas) e `prefers-reduced-motion` é respeitado. JS e CSS de partes novas grandes só são baixados quando usados.
- Sem controles nativos do navegador nos formulários: usar os componentes de `ui.css`.
- Ícones: só os do conjunto de `_icones.html` (acrescentar no mesmo traço, se faltar).
- Acessibilidade: foco visível (azul), navegação por teclado e textos de status lidos por leitor de tela.

## Registro de decisões
- 2026-11-25 — Este resumo foi aprovado pelo Emanuel e vale como base das telas da fase 3 (chat, busca por significado e peças parecidas).
- 2026-11-25 — No computador o chat abre como painel lateral, não em tela inteira — referência da Apple Store, com "evitar tela inteira" escolhido pela dupla. No celular ele pode ocupar a tela, porque não há espaço para um painel ao lado.
- 2026-11-25 — Nada de avatar, mascote ou visual "de IA" no chat — clima "calmo e minimalista" e a lista "nunca parecer".
- 2026-11-25 — Escopo e estados da fase 3 aprovados pelo Emanuel: chat, `/busca` por significado e página do produto.
- 2026-11-25 — A partir de 1280 px o chat fica acoplado à direita (400 px) e a página se estreita, sem véu — por cima, ele cobriria a coluna de compra do produto. Abaixo disso abre por cima, com véu; até 640 px ocupa a tela.
- 2026-11-25 — O carrinho abre por cima do chat acoplado, e ao fechá-lo o chat continua lá — fechar o chat faria a página mudar de largura no meio da animação de "Adicionar ao carrinho".
- 2026-11-25 — Com o chat acoplado, ele continua aberto ao trocar de página (`sessionStorage`) — o cliente abre a peça sugerida sem perder a conversa.
- 2026-11-25 — O cliente vê só o título das fontes citadas, numeradas na ordem da resposta — a porcentagem de similaridade fica no laboratório do painel.
- 2026-11-25 — Limite de perguntas aparece em cinza, com relógio e contagem; vermelho só para falha — é uma pausa, não um erro.
- 2026-11-25 — O botão do chat é branco, não preto — preto é da ação principal de cada tela (ex.: "Adicionar ao carrinho").
- 2026-11-25 — No celular os avisos (`.toasts`) sobem para 84 px quando há botão do chat — senão um cobriria o outro.
- 2026-11-25 — Ícones conversa, enviar, positivo e negativo entraram em `_icones.html` com a geometria do Lucide, no traço do conjunto.
- 2026-11-25 — Importar o design system para o Figma: recusado; o código continua sendo a origem.
- 2026-11-25 — Fase 4 (painel > Assistente IA) aprovada: visão geral, laboratório de RAG, documentos e perguntas, com abas no topo como em Pedidos. O painel é desenhado para computador e tablet.
- 2026-11-25 — No laboratório, as 5 etapas são numeradas porque a ordem é real (pergunta, embedding, busca, prompt, resposta) — é a sequência que o vídeo explica.
- 2026-11-25 — A linha do mínimo de similaridade é laranja (`--laranja`, cor de atenção do painel), não vermelha — vermelho fica para erro.
- 2026-11-25 — Documentos da pasta `conhecimento/` só podem ser desativados no painel; o texto é editado no arquivo — senão a próxima indexação pelo script desfaria a edição.
- 2026-11-25 — Dashboard com 5 bancos (pgvector e Gemini entraram); o tempo de resposta foi para baixo do nome — em 5 colunas ele espremia o texto.

## Perguntas em aberto
- Quem é o cliente da NOMA (idade, perfil)? Hoje é suposição: adultos que compram básicos.
