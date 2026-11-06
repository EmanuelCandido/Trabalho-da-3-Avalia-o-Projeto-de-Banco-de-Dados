# Planejamento — NOMA, e-commerce com banco de dados poliglota

Trabalho da 3ª avaliação de Projeto de Banco de Dados (entrega até 26/11/2026).
Divisão da dupla: as telas foram desenhadas no Figma (loja **NOMA**) e o backend, a integração e a aplicação das telas ficam neste repositório.

## 1. O que o enunciado exige e onde cada item fica

| Exigência | Como atendemos |
|---|---|
| Supabase (PostgreSQL) para autenticação e login do admin | Login do admin pelo **Supabase Auth**; tabelas `administradores`, `acessos_admin`, `pedidos`, `itens_pedido` e `configuracoes` no Postgres do Supabase |
| MongoDB para cadastro e armazenamento dos produtos | Coleção `produtos` com documento flexível (cores, tamanhos, imagens, atributos livres e avaliações embutidas); imagens enviadas pelo admin ficam no **GridFS** |
| Redis como cache de produtos vistos recentemente | Lista `vistos` por visitante, além de carrinho, cache do catálogo, ranking de mais vistos e limite de tentativas de login |
| Tela de login segura | Senha conferida pelo Supabase, sessão assinada, proteção CSRF e bloqueio após 5 tentativas erradas (contador no Redis) |
| Tela de cadastro de produtos | Formulário com nome, descrição, preço, preço promocional, estoque, categoria, gênero, cores, tamanhos, imagens (upload ou URL) e atributos dinâmicos |
| Catálogo público | Página inicial e listagens por categoria lendo do MongoDB, com cache no Redis |
| Carrinho (adicionar, remover, total) | Gaveta lateral do Figma; itens guardados no Redis (hash por visitante) |
| Botão "Comprar" que abre o WhatsApp | O pedido é gravado no Supabase pela função `registrar_pedido` e o cliente é redirecionado para `wa.me` com a mensagem formatada |
| Vídeo de 5 a 10 minutos | Roteiro na seção 8 |

## 2. Arquitetura

```
Navegador ──► Flask (Python)
               ├─ MongoDB Atlas ── produtos, avaliações, imagens (GridFS)
               ├─ Supabase ─────── Auth (login do admin) + PostgreSQL (pedidos, configurações, auditoria)
               └─ Redis ────────── vistos recentemente, carrinho, cache do catálogo, ranking, limite de login
```

Tecnologias: Python 3.12, Flask 3, Jinja2, `pymongo`, `psycopg` 3, `redis-py` e `requests` (API do Supabase Auth). O front usa HTML, CSS e JavaScript puro, sem frameworks, com a fonte Manrope.

### Por que cada banco

- **MongoDB:** cada produto tem campos diferentes (uma polo tem gola e tamanhos; um óculos tem lente e proteção UV). O documento aceita isso sem migração de esquema, e as avaliações ficam embutidas no próprio produto.
- **Supabase/PostgreSQL:** autenticação pronta e segura, além de dados transacionais que precisam de integridade (pedido e itens gravados juntos, numa função PL/pgSQL).
- **Redis:** dados de acesso rápido e vida curta, com expiração automática (TTL): histórico de navegação, carrinho e cache.

## 3. Modelo de dados

### MongoDB — coleção `produtos`

```json
{
  "_id": "ObjectId",
  "slug": "camisa-polo-masculina-classica",
  "nome": "Camisa Polo Masculina Clássica",
  "descricao": "texto longo",
  "categoria": "Roupas | Acessórios",
  "genero": "Masculino | Feminino | Unissex",
  "preco": 299.0,
  "preco_promocional": 239.0,
  "estoque": 18,
  "vendidos": 672,
  "material": "Algodão",
  "composicao": "100% algodão pima",
  "cores": [{"nome": "Dust Beige", "hex": "#b9a7a3"}],
  "tamanhos": ["P", "M", "G", "GG", "XGG"],
  "imagens": ["/static/img/produtos/polo-1.jpg"],
  "destaques": {"oferta": true, "queridinho": false, "novidade": false},
  "atributos": {"Gola": "Polo", "Caimento": "Regular"},
  "avaliacoes": [{"nome": "André L.", "nota": 5, "titulo": "...", "texto": "...", "tamanho": "M", "cor": "Dust Beige", "data": "ISODate"}],
  "ativo": true,
  "criado_em": "ISODate",
  "atualizado_em": "ISODate"
}
```

Índices: `slug` (único), texto em `nome` + `descricao`, `categoria`, `destaques.*` e `ativo`.

### Supabase — PostgreSQL (`database/supabase.sql`)

| Tabela / objeto | Uso |
|---|---|
| `administradores` | Quem pode entrar no painel (e-mail ligado ao usuário do Supabase Auth) |
| `acessos_admin` | Auditoria de cada tentativa de login (sucesso, IP, data) |
| `pedidos` | Pedido enviado ao WhatsApp: código, cliente, total, mensagem e status |
| `itens_pedido` | Itens de cada pedido (produto, cor, tamanho, quantidade e preço) |
| `configuracoes` | Número do WhatsApp, nome da loja e texto da faixa promocional |
| `registrar_pedido(...)` | Função PL/pgSQL que grava o pedido e os itens numa única transação |
| `vw_resumo_vendas` | View usada no dashboard (pedidos, faturamento e ticket médio) |

### Redis — chaves (prefixo `noma:`)

| Chave | Tipo | TTL | Uso |
|---|---|---|---|
| `noma:vistos:{visitante}` | LIST | 30 dias | Últimos 12 produtos abertos (`LREM` + `LPUSH` + `LTRIM`) |
| `noma:carrinho:{visitante}` | HASH | 7 dias | Item `produto|cor|tamanho` → quantidade |
| `noma:cache:v{versao}:{consulta}` | STRING (JSON) | 5 min | Cache-aside das vitrines e listagens |
| `noma:cache:versao` | STRING | — | Incrementada quando o admin salva, invalidando todo o cache |
| `noma:ranking:views` | ZSET | — | Produtos mais vistos (dashboard) |
| `noma:login:falhas:{ip}` | STRING | 15 min | Bloqueio após 5 tentativas erradas |
| `noma:stats` | HASH | — | Acertos (HIT) e faltas (MISS) do cache |

## 4. Telas

### Loja (do Figma)

1. **Início (Catálogo):** faixa "10% OFF EXTRA NO PIX" com contagem regressiva, carrossel de banners (Black Friday e Coleção), "Ofertas da Black", "Veja nossos acessórios", "Os queridinhos" com o cartão de guia de tamanhos, "Vistos recentemente" (Redis) e rodapé.
2. **Listagem (Roupas, Acessórios, Novidades e Ofertas):** título, contagem, filtros (gênero, tamanho, cor, preço e material), ordenação e "Ver mais".
3. **Detalhe do produto:** galeria 2×2, preço com promoção e parcelamento, cor, tamanho, guia de medidas, quantidade, adicionar ao carrinho ou estado "Esgotado", sanfonas (Descrição, Características e Composição), avaliações com distribuição de notas e "Escrever avaliação", e vistos recentemente.
4. **Gaveta do carrinho:** itens com foto, cor/tamanho, quantidade, remover, total, "Finalizar compra" e "Continuar comprando".

### Criadas no mesmo estilo (não estavam no Figma)

5. **Finalizar pedido:** janela com resumo, nome, observação e prévia da mensagem, seguida do redirecionamento ao WhatsApp.
6. **Busca:** painel que desce do topo com resultados ao vivo.
7. **Páginas institucionais:** Sobre a NOMA, Atendimento e Guia de tamanhos.
8. **Admin — Login:** foto do ateliê, formulário, erro com "tremida" e bloqueio por tentativas.
9. **Admin — Dashboard:** totais, faturamento (view do Supabase), mais vistos (Redis), últimos pedidos e status dos três bancos.
10. **Admin — Produtos:** tabela com busca, ativar/desativar e excluir com confirmação.
11. **Admin — Cadastro/edição de produto:** todos os campos, upload com pré-visualização, cores, tamanhos e atributos dinâmicos.
12. **Admin — Pedidos:** lista dos pedidos gravados no Supabase com os itens.
13. **Admin — Configurações:** WhatsApp, nome da loja e faixa promocional.

## 5. Animações e respostas às ações do usuário

- Revelação ao rolar (seções e cards entram com fade-up em cascata).
- Hover no card: zoom suave na foto e troca para a segunda imagem.
- Adicionar ao carrinho: a foto "voa" até o ícone do carrinho, o contador pulsa, o botão vira "Adicionado ✓" e a gaveta desliza.
- Gaveta: itens entram em cascata, o item removido recolhe, e quantidade e total são animados.
- Tentar comprar sem escolher tamanho: o seletor treme e aparece um aviso.
- Carrossel com transição suave e zoom lento; contagem regressiva ao vivo.
- Sanfonas com altura animada; estrelas reagem ao passar o mouse.
- Finalizar: botão com carregamento, check animado e redirecionamento.
- Toasts deslizantes para sucesso e erro.
- Admin: login que treme no erro, linhas que recolhem ao excluir, interruptor animado, pré-visualização da imagem e atributos que entram e saem animados.
- Esqueleto com brilho enquanto as imagens carregam; respeita `prefers-reduced-motion`.

## 6. Conteúdo fictício

18 produtos (os 15 do Figma e 3 novidades), com fotos geradas pelo gerador de imagens do Codex no mesmo estilo de estúdio do Figma, além dos banners da Black Friday e da Coleção e da foto do login do admin. Os ícones são SVG desenhados no próprio código, para ficarem nítidos em qualquer tamanho.

## 7. Etapas

1. Estrutura do projeto, configuração (`.env`) e conexões.
2. Camadas de dados: `bancos/mongo.py`, `bancos/supabase.py` e `bancos/redis_store.py`.
3. Scripts: `database/supabase.sql`, `scripts/setup_supabase.py` (tabelas + admin) e `scripts/seed.py` (produtos).
4. Rotas da loja e API JSON do carrinho e do pedido.
5. Rotas do admin (login, dashboard, CRUD, pedidos e configurações).
6. Templates e CSS fiéis ao Figma; JavaScript das interações e animações.
7. Testes manuais do fluxo completo no navegador (desktop e celular).
8. README com instruções de configuração dos bancos, commit e push.

## 8. Roteiro do vídeo (5 a 10 min)

1. Arquitetura em 30 s: os três bancos e o papel de cada um.
2. Login do admin (mostrar também o erro e o registro em `acessos_admin` no Supabase).
3. Cadastro de um produto novo, com foto e atributos extras; mostrar o documento no MongoDB.
4. Abrir a loja: o produto aparece na hora (o cache foi invalidado no Redis).
5. Abrir alguns produtos e mostrar "Vistos recentemente" e a lista no Redis.
6. Adicionar ao carrinho, alterar quantidades, remover e ver o total.
7. Finalizar: redirecionamento ao WhatsApp com a mensagem formatada; mostrar o pedido gravado no Supabase.
