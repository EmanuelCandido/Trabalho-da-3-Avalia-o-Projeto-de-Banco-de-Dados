"""Cliente da API do Gemini por REST (só `requests`, sem SDK).

- embeddings(): transforma textos em vetores (gemini-embedding-001, 768 dimensões)
- responder():  escreve a resposta a partir do prompt montado pelo RAG

A chave vai no cabeçalho x-goog-api-key, nunca na URL (assim ela não aparece em logs de acesso).
"""
import math
import time

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
LOTE = 50              # textos por chamada de batchEmbedContents
TENTATIVAS = 4         # 429 (cota) e 5xx são tentados de novo, com espera crescente

_cfg = {"chave": "", "modelo": "", "modelo_embedding": "", "dim": 768}


class ErroIA(Exception):
    """Falha ao falar com o Gemini (cota, rede, chave inválida). A mensagem pode ir para o log, não para o cliente."""


def init(chave, modelo, modelo_embedding, dim):
    _cfg.update(chave=chave or "", modelo=modelo, modelo_embedding=modelo_embedding, dim=int(dim))


def ativo():
    return bool(_cfg["chave"])


def modelo():
    return _cfg["modelo"]


def modelo_embedding():
    """Nome gravado na coluna conhecimento.modelo: vetores de modelos ou tamanhos diferentes não se comparam."""
    return f"{_cfg['modelo_embedding']}@{_cfg['dim']}"


def dimensoes():
    return _cfg["dim"]


def _post(caminho, corpo, timeout=30):
    if not ativo():
        raise ErroIA("GEMINI_API_KEY não configurada.")
    for tentativa in range(TENTATIVAS):
        try:
            r = requests.post(f"{BASE}/{caminho}", json=corpo, timeout=timeout,
                              headers={"x-goog-api-key": _cfg["chave"], "Content-Type": "application/json"})
        except requests.RequestException as erro:
            if tentativa < TENTATIVAS - 1:
                time.sleep(2 ** tentativa)
                continue
            raise ErroIA(f"Sem conexão com o Gemini: {erro.__class__.__name__}") from erro
        if r.status_code in (429, 500, 502, 503, 504) and tentativa < TENTATIVAS - 1:
            espera = r.headers.get("Retry-After")
            time.sleep(min(float(espera) if espera and espera.isdigit() else 2 ** (tentativa + 1), 20))
            continue
        if r.status_code != 200:
            try:
                mensagem = r.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                mensagem = r.text[:200]
            raise ErroIA(f"Gemini respondeu {r.status_code}: {mensagem}")
        return r.json()
    raise ErroIA("Gemini não respondeu depois de várias tentativas.")


def normalizar(vetor):
    """Deixa o vetor com tamanho 1. O Gemini só normaliza o vetor de 3072 dimensões; com 768 a gente normaliza.
    A distância de cosseno não muda, mas o produto interno (<#>) passa a dar o mesmo resultado."""
    norma = math.sqrt(sum(v * v for v in vetor)) or 1.0
    return [v / norma for v in vetor]


def embeddings(textos, tipo="RETRIEVAL_DOCUMENT", titulos=None):
    """Lista de textos -> lista de vetores.
    tipo: RETRIEVAL_DOCUMENT para o que é guardado e RETRIEVAL_QUERY para a pergunta do usuário
    (o modelo gera vetores ajustados para cada lado da busca)."""
    vetores = []
    for inicio in range(0, len(textos), LOTE):
        pedidos = []
        for i, texto in enumerate(textos[inicio:inicio + LOTE], start=inicio):
            pedido = {"model": f"models/{_cfg['modelo_embedding']}", "content": {"parts": [{"text": texto}]},
                      "taskType": tipo, "outputDimensionality": _cfg["dim"]}
            if tipo == "RETRIEVAL_DOCUMENT" and titulos and titulos[i]:
                pedido["title"] = titulos[i]
            pedidos.append(pedido)
        dados = _post(f"models/{_cfg['modelo_embedding']}:batchEmbedContents", {"requests": pedidos})
        vetores.extend(normalizar(e["values"]) for e in dados.get("embeddings", []))
    if len(vetores) != len(textos):
        raise ErroIA(f"O Gemini devolveu {len(vetores)} vetores para {len(textos)} textos.")
    return vetores


def embedding(texto, tipo="RETRIEVAL_QUERY"):
    return embeddings([texto], tipo)[0]


def _config_raciocinio():
    """Modelos com "raciocínio" gastam tokens pensando antes de responder. Para respostas curtas de loja
    isso só deixa mais lento: no 2.5 Flash desligamos; na família 3 usamos o nível mais baixo."""
    nome = _cfg["modelo"]
    if "2.5-flash" in nome:
        return {"thinkingBudget": 0}
    if nome.startswith("gemini-3"):
        return {"thinkingLevel": "low"}
    return None


def responder(sistema, mensagens, temperatura=0.3, max_tokens=1024):
    """mensagens: [{"papel": "usuario" | "modelo", "texto": "..."}]. Devolve texto, tokens e o motivo do fim."""
    corpo = {
        "systemInstruction": {"parts": [{"text": sistema}]},
        "contents": [{"role": "model" if m["papel"] == "modelo" else "user", "parts": [{"text": m["texto"]}]}
                     for m in mensagens],
        "generationConfig": {"temperature": temperatura, "maxOutputTokens": max_tokens},
    }
    raciocinio = _config_raciocinio()
    if raciocinio:
        corpo["generationConfig"]["thinkingConfig"] = raciocinio
    dados = _post(f"models/{_cfg['modelo']}:generateContent", corpo, timeout=45)
    candidato = (dados.get("candidates") or [{}])[0]
    partes = (candidato.get("content") or {}).get("parts") or []
    texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))
    uso = dados.get("usageMetadata") or {}
    if not texto.strip():
        motivo = candidato.get("finishReason") or (dados.get("promptFeedback") or {}).get("blockReason")
        raise ErroIA(f"O Gemini não devolveu texto (motivo: {motivo}).")
    return {"texto": texto.strip(), "tokens_entrada": uso.get("promptTokenCount"),
            "tokens_saida": uso.get("candidatesTokenCount"), "motivo": candidato.get("finishReason")}
