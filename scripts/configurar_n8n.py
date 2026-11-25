"""Configura o n8n local (bônus do trabalho): variáveis no .env, contêiner, credencial e os dois workflows.

Uso (com o Docker Desktop aberto):
    python scripts/configurar_n8n.py

O que ele faz, nesta ordem:
  1. completa o .env com N8N_SEGREDO, N8N_WEBHOOK_URL e N8N_PG_* (tirados da DATABASE_URL, porta 5432);
  2. sobe o contêiner: docker compose --profile n8n up -d n8n;
  3. importa n8n/credencial-postgres.json e os workflows n8n/indexar-produto.json e n8n/reindexacao-noturna.json;
  4. publica (ativa) os dois workflows e reinicia o n8n para o webhook entrar no ar.
Pode rodar de novo: os workflows e a credencial são substituídos pelos arquivos da pasta n8n/.

Depois, reinicie o Flask (python app.py) para ele ler o N8N_SEGREDO e o N8N_WEBHOOK_URL do .env.
"""
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests

RAIZ = Path(__file__).resolve().parent.parent
ENV = RAIZ / ".env"
CONTEINER = "trabalho3avaliao-n8n-1"
ARQUIVOS = ["credencial-postgres", "indexar-produto", "reindexacao-noturna"]
WORKFLOWS = ["NomaIndexarProd1", "NomaReindexNoite"]


def rodar(*cmd, checar=True):
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if checar and r.returncode != 0:
        sys.exit(f"Falhou: {' '.join(cmd)}\n{(r.stderr or r.stdout)[-800:]}")
    return r.stdout


def completar_env():
    texto = ENV.read_text(encoding="utf-8")

    def valor(nome):
        m = re.search(rf"^{nome}=(.*)$", texto, re.M)
        return m.group(1).strip().strip("'\"") if m else ""

    url = urlsplit(valor("DATABASE_URL"))
    if not url.hostname:
        sys.exit("Preencha a DATABASE_URL no .env antes.")
    novas = {"N8N_SEGREDO": valor("N8N_SEGREDO") or secrets.token_urlsafe(32),
             "N8N_WEBHOOK_URL": valor("N8N_WEBHOOK_URL") or "http://localhost:5678/webhook/noma-indexar",
             "N8N_PG_HOST": url.hostname, "N8N_PG_USER": url.username or "postgres",
             "N8N_PG_SENHA": unquote(url.password or ""), "N8N_PG_BANCO": url.path.lstrip("/") or "postgres"}
    for nome, v in novas.items():
        # Aspas simples: o Docker Compose não troca "$..." dentro delas (senhas do Supabase podem ter $).
        linha = f"{nome}='{v}'" if "$" in v else f"{nome}={v}"
        if re.search(rf"^{nome}=", texto, re.M):
            texto = re.sub(rf"^{nome}=.*$", lambda _: linha, texto, flags=re.M)
        else:
            texto = texto.rstrip("\n") + f"\n{linha}"
    ENV.write_text(texto.rstrip("\n") + "\n", encoding="utf-8")
    print("1. .env completo (N8N_SEGREDO, N8N_WEBHOOK_URL e N8N_PG_*)")


def esperar_n8n():
    for _ in range(60):
        try:
            if requests.get("http://127.0.0.1:5678/healthz", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    sys.exit("O n8n não respondeu em http://127.0.0.1:5678/healthz.")


def main():
    completar_env()
    rodar("docker", "compose", "--profile", "n8n", "up", "-d", "n8n")
    esperar_n8n()
    print("2. n8n no ar em http://localhost:5678")
    for nome in ARQUIVOS:
        rodar("docker", "cp", str(RAIZ / "n8n" / f"{nome}.json"), f"{CONTEINER}:/tmp/{nome}.json")
    rodar("docker", "exec", CONTEINER, "n8n", "import:credentials", "--input=/tmp/credencial-postgres.json")
    for nome in ARQUIVOS[1:]:
        rodar("docker", "exec", CONTEINER, "n8n", "import:workflow", f"--input=/tmp/{nome}.json")
    print("3. credencial e workflows importados")
    for wid in WORKFLOWS:
        rodar("docker", "exec", CONTEINER, "n8n", "publish:workflow", f"--id={wid}")
    rodar("docker", "restart", CONTEINER)
    esperar_n8n()
    print("4. workflows publicados. Webhook: POST http://localhost:5678/webhook/noma-indexar")
    print("\nPronto. Reinicie o Flask para ele usar o n8n. No primeiro acesso a http://localhost:5678, "
          "crie a sua conta de dono para ver os workflows e as execuções.")


if __name__ == "__main__":
    main()
