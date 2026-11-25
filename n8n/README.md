# n8n: o pipeline que mantém o banco vetorial em dia

O n8n roda localmente no Docker e cuida da **indexação**: quando um produto muda no MongoDB, os vetores dele no pgvector (Supabase) precisam mudar também. A loja funciona sem ele: se o n8n estiver desligado, o próprio Python indexa (`ia/indexador.py`).

| Arquivo | O que é |
|---|---|
| `indexar-produto.json` | Workflow **NOMA · Indexar produto** (webhook chamado pelo painel ao salvar, excluir, ativar ou desativar um produto) |
| `reindexacao-noturna.json` | Workflow **NOMA · Reindexação noturna** (todo dia às 3h confere o catálogo inteiro) |
| `credencial-postgres.json` | Credencial do Postgres **sem senha**: os campos apontam para variáveis de ambiente (`$env.NOMA_PG_*`) |

Nenhum segredo fica nos arquivos. O `docker-compose.yml` passa ao contêiner, a partir do `.env`, o `N8N_SEGREDO`, a `GEMINI_API_KEY` e os dados do Postgres, e os nós leem com `{{ $env.NOME }}`.

## Workflow "Indexar produto"

```
Webhook (POST /webhook/noma-indexar)
  → Segredo e id conferem?  ── não → Recusar (401)
  → Textos do produto (Flask)        GET /api/interno/produto/<id>/documentos
  → Hashes no pgvector               select … from conhecimento where referencia = $1
  → Separar o que mudou              compara o sha256 de cada trecho com o que está no banco
  → Tem trecho novo?  ── não ──────────────────────────────┐
  → Gemini: embeddings               batchEmbedContents, 768 dimensões, RETRIEVAL_DOCUMENT
  → Normalizar vetores               tamanho 1, igual ao Python
  → Gravar no pgvector               insert … on conflict do update (um insert para todos)
  → Apagar sobras e registrar  ◄───────────────────────────┘   delete + insert em indexacoes
  → Responder ao painel              {"ok": true, "novos": 1, "iguais": 1, "removidos": 0}
```

- O texto de cada produto é montado pelo Flask (o mesmo código que o Python usa para indexar). Assim o n8n e o Python geram exatamente os mesmos vetores.
- Preço e estoque não entram no vetor: uma venda nunca gera embedding novo.
- Produto excluído ou desativado: o Flask devolve a lista de trechos vazia e o workflow apaga os vetores dele.
- O embedding sai de um **HTTP Request**, e não do nó "Embeddings Google Gemini" do n8n: aquele nó gera 3072 dimensões fixas, e o índice HNSW do pgvector aceita no máximo 2000.

## Workflow "Reindexação noturna"

`Todo dia às 3h` (ou `Executar agora`) → produtos ativos no Flask → produtos que têm vetores no banco → um item por produto → chama o webhook acima para cada um → resumo (`produtos`, `novos`, `iguais`, `removidos`). Corrige qualquer chamada que tenha falhado durante o dia.

## Como rodar

Com o Docker Desktop aberto e o `.env` preenchido (`DATABASE_URL` e `GEMINI_API_KEY`):

```powershell
python scripts/configurar_n8n.py
```

O script completa o `.env` (`N8N_SEGREDO`, `N8N_WEBHOOK_URL` e `N8N_PG_*`), sobe o contêiner, importa a credencial e os workflows e os publica. Depois, reinicie o Flask (`python app.py`) para ele chamar o n8n ao salvar um produto.

No primeiro acesso a http://localhost:5678, o n8n pede para criar a conta de dono (é local, fica só no volume do Docker). Depois disso aparecem os dois workflows e, em **Executions**, cada execução com os dados de cada nó.

Para conferir sem abrir o painel:

```powershell
docker compose --profile n8n logs -f n8n
```

## Detalhes que costumam travar

- **Porta 5432, não 6543.** O n8n conecta no pooler do Supabase em modo sessão (5432). O Python usa o modo transação (6543).
- **Senha com `$`.** O Docker Compose troca `$NOME` por variáveis. O script grava a senha entre aspas simples no `.env`, que o Compose lê literalmente.
- **`host.docker.internal`.** É o endereço do computador visto de dentro do contêiner (o Flask em `localhost:5000`).
- **Webhook de produção.** O painel chama `/webhook/noma-indexar`, que só responde com o workflow publicado. A URL `/webhook-test/` só funciona enquanto o editor está escutando.
- **Online (Vercel) não há n8n.** Lá o Python indexa sozinho; a variável `N8N_WEBHOOK_URL` fica vazia.
