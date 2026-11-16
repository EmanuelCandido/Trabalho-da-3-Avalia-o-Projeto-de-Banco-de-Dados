# Vídeo de demonstração — análise da referência, planejamento e produção

Entrega: vídeo de 5 a 10 minutos mostrando o sistema em execução, com **obrigatoriamente**:

1. o login do administrador;
2. o cadastro de um produto novo e a atualização imediata no catálogo do cliente;
3. a simulação de uma compra com o redirecionamento correto e a mensagem formatada para o WhatsApp.

A referência de estilo é o teaser "Meet Goose" (`ssstwitter.com_1794522473248.mp4`). Este documento explica o que define esse estilo, como ele foi adaptado para uma demonstração de ~5 min 40 s e como o vídeo é produzido pelo código em [`video/`](../video).

---

## 1. Análise do vídeo de referência

### 1.1 Ficha técnica

| Item | Valor |
|---|---|
| Duração | 17,8 s |
| Resolução / quadros | 1920×1080, **60 fps**, H.264 |
| Áudio | AAC 48 kHz estéreo, **sem música e sem narração**: só efeitos sonoros, com silêncio absoluto entre eles |
| Cortes secos | Nenhum. Toda troca de cena é um movimento (deslize, zoom, encolher, cortina) |

### 1.2 Decupagem (o que acontece a cada instante)

| Tempo | Imagem | Técnica |
|---|---|---|
| 0,0–0,3 s | "Meet" e "Goose" surgem desfocados e ficam nítidos | Texto com desfoque → nitidez (≈200 ms) |
| 0,6–1,2 s | Um cartão com a foto do pato nasce entre as palavras e outros 4 cartões abrem em leque atrás dele | Escala com mola + leque com rotação |
| 1,5–2,9 s | As palavras viram frases: "Goose is an / AI coworker" à esquerda, "that can do / real GTM work" à direita | Palavra a palavra, desfoque → nitidez |
| 3,0–3,2 s | Tudo sobe rápido e sai; o Dock do Mac sobe por baixo | Chicote vertical (*whip pan*) com borrão de movimento |
| 3,2–4,2 s | O cursor entra pela direita, passa por baixo dos ícones e clica no Slack (vira mãozinha) | Cursor grande, com rastro, aceleração suave |
| 4,5–5,8 s | Só a caixa de mensagem do Slack, sozinha no branco, com o texto sendo digitado | Elemento de interface **isolado** |
| 6,0–7,1 s | A câmera se afasta, mostra a janela inteira do Slack e a janela encolhe | Recorte que se expande + zoom para fora |
| 7,2–9,8 s | De volta ao Dock; o cursor seleciona Mensagens e Mail | Retorno ao "hub" de navegação |
| 10,0–10,4 s | Dock sobe, um iPhone sobe por baixo | Deslize vertical encadeado |
| 10,6–13,7 s | Balões do iMessage aparecem com "pop" e o campo de texto é digitado | Balão desfocado → nítido, com leve elástico |
| 13,8–14,2 s | Celular desfoca e sai; o botão azul "Compose" é digitado letra a letra | Troca por desfoque |
| 14,5–15,5 s | Clique no botão; um papel de parede de céu entra pela direita como cortina | Cortina lateral |
| 15,5–17,8 s | Uma janela "New Message" abre a partir de um ponto e o cursor vai até "Send" | Janela que cresce de um ponto (escala 0 → 1) |

### 1.3 O que torna o estilo reconhecível

- **Fundo branco puro** e muito espaço vazio. A cor vem só das interfaces e de um único "fundo especial" (o céu).
- **Tipografia** sem serifa estilo Apple (SF Pro), peso médio, preta, ~48 px em 1080p, frases curtas de 2 a 4 palavras divididas em duas colunas ao redor de um objeto central.
- **Tudo entra com desfoque**: textos, balões e botões começam borrados e transparentes e ficam nítidos em 150–300 ms.
- **Interface isolada**: em vez de mostrar a tela inteira, mostra só o pedaço que importa (a caixa de mensagem, o botão), flutuando no branco com sombra suave; depois a câmera se afasta para dar contexto.
- **Câmera sempre em movimento**: leve aproximação contínua, zoom para dentro e para fora, e chicotes rápidos entre cenas. Nada fica parado mais de ~1,5 s.
- **Cursor protagonista**: seta do macOS grande (~1,6×), com rastro em movimentos rápidos, virando mãozinha sobre o que é clicável e "afundando" no clique.
- **Curvas de animação** com saída rápida e chegada macia (*ease-out*) e um pouco de mola (passa do ponto e volta) nos objetos que aparecem.
- **Som** só de interface: clique, teclado, "whoosh" nas transições e "pop" quando algo aparece. Entre eles, silêncio.
- **Ritmo**: uma ação nova a cada ~1 s; cada cena dura de 2 a 4 s.

---

## 2. Adaptação para uma demonstração de ~5 min 40 s

O teaser tem 18 s e telas simuladas; a entrega exige **gravação do sistema real** por 5 a 10 minutos. A adaptação mantém a gramática visual e muda o ritmo:

| Na referência | No nosso vídeo |
|---|---|
| Telas desenhadas | **Gravação real** do navegador rodando a NOMA (Flask + MongoDB + Supabase + Redis), exibida como janela flutuando no branco |
| Interface isolada (caixa do Slack) | O formulário de login e o botão "Finalizar compra" aparecem **recortados** da gravação real e depois a câmera se afasta para a janela inteira |
| Zoom e chicote | Zoom automático no campo que está sendo usado (estilo Screen Studio) e chicote entre capítulos |
| Dock do Mac | Dock próprio com os ícones **Loja, Painel, MongoDB, Supabase, Redis e WhatsApp** (ícones desenhados no código, sem logotipos oficiais), usado como "mapa" entre capítulos |
| iPhone com iMessage | Celular com a conversa do WhatsApp mostrando **a mensagem real do pedido** (o texto vem da URL gravada) |
| Cortina de céu | Fundo azul entra pela direita quando o cliente clica em "Finalizar compra" |
| Frases ao lado do objeto | Legendas curtas, palavra a palavra, explicando **qual banco faz o quê** em cada momento |
| Sem narração | Mantido: legendas na tela explicam tudo. A seção 7 traz um texto opcional de narração |

---

## 3. Guia de estilo (valores usados no código)

| Elemento | Valor |
|---|---|
| Fundo | `#FFFFFF`; fundo especial azul `#3f8fe6 → #8cc4f5` (cortina da compra) |
| Texto | Inter 500, `#111`, 56 px (títulos) / 30 px (legendas), espaçamento −0,02 em |
| Texto secundário | `#8a8a8a`, Inter 500 |
| Entrada de palavra | opacidade 0→1, desfoque 14 px→0, deslocamento 10 px→0, 320 ms, *ease-out cubic*, 70 ms entre palavras |
| Janela do navegador | cantos 14 px, barra clara com endereço real, sombra `0 40px 90px rgba(0,0,0,.14)` |
| Zoom de câmera | 1× a 2,1×, transição de 0,9 s *ease-in-out*, sempre centrado no elemento em uso |
| Chicote | 0,45 s, deslocamento de 1 tela com borrão vertical |
| Cursor | seta do macOS 34 px, mãozinha sobre clicáveis, clique = escala 0,82 por 120 ms |
| Mola | sobressalto de ~6% ao aparecer (cartões, balões, ícones) |
| Saída | 1920×1080, 60 fps, H.264 CRF 18, AAC 192 kbps |
| Sons | picos de clique −10 dB, tecla −19 dB (com variação aleatória), whoosh −12 dB, pop −13 dB, tique −21 dB, sucesso −11 dB; limitador em −1,5 dB. Sem música |

---

## 4. Roteiro e storyboard (≈ 5 min 40 s)

Os tempos são aproximados; a montagem ajusta as pausas da gravação (esperas de rede são aceleradas).

### Cena 0 — Abertura (0:00–0:08)
- "Conheça" e "a NOMA" surgem com desfoque; entre as palavras, um cartão com a foto de um produto cresce e outros quatro abrem em leque (polo, vestido, bolsa, óculos, tricô).
- As palavras viram frases: **"Uma loja de roupas"** / **"com três bancos de dados"**. Abaixo, em cinza: "Projeto de Banco de Dados · 3ª avaliação".
- Chicote para cima; o Dock sobe com os 6 ícones. *(Referência: 0:00–0:04)*

### Cena 1 — Dock e arquitetura (0:08–0:35)
- O cursor percorre o Dock; ao passar em cada banco, um cartão sobe com o papel dele, digitado:
  - **MongoDB** — produtos, fotos (GridFS) e banners.
  - **Supabase** — login do admin, auditoria e pedidos (PostgreSQL).
  - **Redis** — cache do catálogo, carrinho, vistos e bloqueio de login.
- Fecha com o diagrama: Flask → três bancos, com as linhas sendo desenhadas e pontos "viajando" por elas.

### Cena 2 — Login do administrador (0:35–1:15) ✅ exigência 1
- Título de capítulo "01 · Login do administrador".
- Clique no ícone **Painel** do Dock → o formulário de login aparece **isolado** no branco.
- Digita o e-mail e uma senha **errada** → "Entrar" → o formulário treme e avisa as tentativas restantes. Legenda: *"Senha errada: tentativa gravada no Supabase e contada no Redis"*.
- O recorte se expande para a página inteira (foto do ateliê + formulário).
- Digita a senha certa (aparece mascarada) → entra no dashboard. Legenda: *"Supabase Auth confirmou · sessão nova e proteção CSRF"*.
- Zoom no status dos três bancos e em "Acessos recentes", onde aparecem a tentativa errada e a certa.

### Cena 3 — Cadastro de produto (1:15–2:38) ✅ exigência 2 (parte 1)
- Antes do cadastro, a gravação da loja já está aberta em **Novidades** (sem o produto).
- Título "02 · Cadastro de produto". Produtos → Novo produto.
- Preenche, com zoom em cada cartão do formulário (a prévia do card na loja atualiza ao vivo):

  | Campo | Valor |
  |---|---|
  | Nome | Suéter Tricô Vinho |
  | Descrição | Tricô de algodão com ponto inglês, gola careca e punhos canelados. Aquece sem pesar. |
  | Categoria / Gênero | Roupas / Unissex |
  | Preço / Promocional / Estoque | 289,90 / 239,90 / 24 |
  | Material / Composição | Algodão / 100% algodão. Lavar à mão e secar à sombra. |
  | Atributos extras | Gola: Careca · Ponto: Inglês · Caimento: Regular |
  | Fotos | 2 fotos enviadas (vão para o GridFS em WebP) |
  | Cor / Tamanhos | Vinho `#7a1f2b` (da paleta do formulário) / P, M, G, GG |
  | Vitrine | Novidades + Visível na loja |

- "Cadastrar produto" → mensagem "cadastrado no MongoDB e já visível na loja". Cartões flutuantes: **MongoDB · insert em `produtos`** e **Redis · `INCR noma:cache:versao`**.
- Clique em "Ver documento no MongoDB" → o JSON real aparece; zoom em `atributos`.

### Cena 4 — Atualização imediata no catálogo (2:38–3:15) ✅ exigência 2 (parte 2)
- Título "03 · O catálogo do cliente na hora".
- Tela dividida: à esquerda o painel com o aviso de sucesso; à direita a loja do cliente em **Novidades**, ainda sem o produto. O cliente clica em "Novidades" no menu e o Suéter aparece em primeiro.
- A janela da loja ocupa a tela: o mouse passa no card (troca para a segunda foto), a **busca ao vivo** encontra "tricô vinho" e abre o produto (galeria com as duas fotos, preço com desconto, cor, tamanhos e "Características" com os atributos livres). Legenda: *"Lido do MongoDB, com cache no Redis"*.

### Cena 5 — Simulação de compra (3:15–4:32) ✅ exigência 3
- Título "04 · Simulação de compra".
- Escolhe M, quantidade 2, "Adicionar ao carrinho" (a foto voa até o carrinho e a gaveta abre). Legenda: *"Carrinho guardado no Redis"*.
- Vai em Acessórios e abre o Cinto de couro; rola até **Vistos recentemente** (LIST no Redis, com o Suéter visto antes) e adiciona o cinto.
- Na gaveta, + e − na quantidade do cinto: total animado (HINCRBY no Redis).
- O botão **"Finalizar compra"** aparece isolado; clique → a cortina azul entra pela direita e a janela de finalização cresce sobre ela.
- Digita nome e observação; zoom na prévia da mensagem. "Enviar pedido pelo WhatsApp" → check animado com o código `NOMA-000xx`.
- Redirecionamento: a barra de endereço mostra `api.whatsapp.com/send?phone=…&text=…` e a página do WhatsApp exibe a mensagem pronta. Zoom no texto.
- Celular sobe com a conversa do WhatsApp e o balão com **a mesma mensagem** aparece com "pop".

### Cena 6 — Pedido gravado no Supabase (4:32–5:10)
- De volta ao painel → Pedidos: o pedido aparece com itens, total e a mensagem enviada. Legenda: *"`registrar_pedido()` grava pedido e itens numa transação"*.
- Dashboard de novo: os totais já contam o pedido; zoom em "Mais vistos" (ZSET do Redis) e em "Comandos recentes no Redis" (HIT/MISS do cache).

### Cena 6b — O que cada banco fez (5:10–5:27)
- Três colunas (MongoDB, Supabase, Redis) e, em cada uma, as operações reais que apareceram no vídeo, marcadas uma a uma: `insert` em `produtos`, fotos no GridFS, `registrar_pedido()`, `acessos_admin`, `INCR` da versão do cache, `HINCRBY` no carrinho, `LPUSH` dos vistos, `ZINCRBY` do ranking.

### Cena 7 — Encerramento (5:27–5:40)
- Frases em sequência: "Login seguro." "Cadastro no MongoDB." "Catálogo ao vivo." "Pedido no WhatsApp."
- O leque de produtos fecha no nome **NOMA**; fade para o branco.

---

## 5. Processo de produção

```
video/fotos.py      → gera as fotos do produto novo (recolore o tricô verde da loja para vinho)
video/capturar.py   → grava o sistema real com o Playwright (Chrome) e salva quadros + eventos
video/montar.py     → monta o vídeo quadro a quadro (animações + gravações + cursor + legendas) e o áudio
video/render/       → página HTML/CSS/JS que desenha cada quadro (o "motor" de animação)
video/sons.py       → sintetiza os efeitos sonoros e mixa a trilha
```

### 5.1 Captura (`capturar.py`)
- Abre dois contextos do Chrome: **admin** e **cliente** (cookies separados, como duas pessoas diferentes), em 1440×900 com densidade 2× (imagem nítida para os zooms).
- Grava cada aba com o *screencast* do Chrome (DevTools Protocol): um JPEG por quadro, com horário.
- Executa o roteiro sozinho: move o mouse em curvas suaves, digita com ritmo humano, rola a página devagar e registra cada movimento, clique, tecla, endereço e a área de cada elemento usado (para o zoom).
- Saída fora do OneDrive (`%LOCALAPPDATA%\noma-video\captura`), para não sincronizar milhares de arquivos.
- A senha do admin é lida do `.env` **na hora em que você roda o script**; ela aparece mascarada na gravação e não fica salva em nenhum arquivo do vídeo.

### 5.2 Montagem (`montar.py` + `render/`)
- Uma página HTML (1920×1080) recebe o tempo `t` e desenha aquele quadro: cenas animadas, janela flutuante com o quadro gravado mais próximo, câmera, cursor e legendas. Tudo é função do tempo, então o resultado é idêntico a cada renderização.
- O Playwright tira a foto de cada quadro e envia direto para o `ffmpeg` (sem salvar milhares de imagens).
- Esperas de rede da gravação são aceleradas; digitação e cliques ficam em tempo real.

### 5.3 Áudio (`sons.py`)
- Os efeitos são sintetizados em Python (ruído filtrado e senoides), então não há direitos autorais envolvidos.
- Cada clique, tecla, transição e aparecimento vira um evento na linha do tempo; a mixagem normaliza o volume e deixa silêncio entre os sons, como na referência.

### 5.4 Comandos

```bash
python video/fotos.py
python video/capturar.py
python video/montar.py
```

O vídeo final sai em `video/saida/NOMA-demo.mp4`.

- `capturar.py` leva ~5 min e precisa só do `.env` preenchido (sobe a loja sozinho se ela não estiver rodando). Use `--ver` para acompanhar a janela do Chrome.
- Antes de gravar, ele apaga o "Suéter Tricô Vinho" de uma gravação anterior, para o vídeo mostrar o produto sendo criado do zero.
- A gravação faz um **pedido real** (fica em *Pedidos* e soma no faturamento) e registra uma tentativa de login errada em `acessos_admin`. É exatamente o que o vídeo precisa mostrar.
- `montar.py` leva ~8 min (vários Chromes em paralelo). Para revisar um instante sem gerar o vídeo todo: `python video/montar.py --quadros 40 95.5`.
- Dependências extras só para o vídeo: `pip install playwright imageio-ffmpeg numpy scipy pillow` e o Google Chrome instalado.

---

## 6. Checklist antes de entregar

- [ ] Duração entre 5 e 10 min.
- [ ] Login aparece do começo ao fim (erro + acerto), com a senha mascarada.
- [ ] O produto é cadastrado na gravação e aparece na loja sem reiniciar nada.
- [ ] A compra termina na página do WhatsApp com a mensagem formatada visível e legível.
- [ ] Nada de `.env`, chaves ou senhas na tela.
- [ ] Legendas legíveis em tela cheia e no celular (mínimo 30 px em 1080p).
- [ ] Áudio sem estouro (pico abaixo de −1 dB).
- [ ] O número de WhatsApp que aparece no vídeo é o configurado em *Configurações* (trocar antes, se não quiser mostrar um número pessoal).

---

## 7. Narração opcional

O vídeo funciona sem voz, como a referência. Se o professor preferir narração, este texto acompanha as cenas:

1. *"Esta é a NOMA, uma loja de roupas que usa três bancos de dados, cada um onde ele é mais forte."*
2. *"O MongoDB guarda os produtos e as fotos; o Supabase cuida do login e dos pedidos; o Redis acelera o catálogo e guarda o carrinho."*
3. *"O administrador entra pelo Supabase Auth. Uma senha errada é registrada e contada no Redis; depois de cinco, o acesso é bloqueado por quinze minutos."*
4. *"No cadastro, cada produto pode ter atributos próprios, porque o documento do MongoDB é flexível. As fotos vão para o GridFS."*
5. *"Ao salvar, o painel invalida o cache no Redis, e a loja do cliente já mostra o produto novo."*
6. *"O cliente escolhe tamanho e quantidade; o carrinho fica no Redis. Ao finalizar, o pedido é gravado no Supabase numa transação e o cliente vai para o WhatsApp com a mensagem pronta."*
7. *"E o pedido aparece no painel, com os itens e a mensagem enviada."*
