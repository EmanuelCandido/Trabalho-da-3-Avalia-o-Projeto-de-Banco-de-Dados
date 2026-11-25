"""Configuração lida do arquivo .env (que não vai para o GitHub)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(nome, padrao=False):
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or "troque-esta-chave-no-env"

    # MongoDB: produtos, avaliações e imagens (GridFS)
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
    MONGO_DB = os.getenv("MONGO_DB", "noma")

    # Supabase: Auth (login do admin) + PostgreSQL (pedidos, configurações, auditoria)
    SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    # Redis: vistos recentemente, carrinho, cache, ranking e limite de login
    REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

    # Número que recebe os pedidos (só dígitos, com DDI e DDD). A tela de configurações do admin
    # sobrescreve este valor gravando na tabela "configuracoes" do Supabase.
    WHATSAPP_NUMERO = os.getenv("WHATSAPP_NUMERO", "5583999999999")

    # IA (RAG): embeddings e respostas do Gemini; os vetores ficam no pgvector do Supabase.
    # Sem GEMINI_API_KEY a loja funciona como antes (sem assistente e com a busca por texto).
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODELO = os.getenv("GEMINI_MODELO", "gemini-3.5-flash-lite")
    GEMINI_MODELO_RESERVA = os.getenv("GEMINI_MODELO_RESERVA", "gemini-flash-lite-latest,gemini-3.6-flash")
    GEMINI_MODELO_EMBEDDING = os.getenv("GEMINI_MODELO_EMBEDDING", "gemini-embedding-001")
    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
    RAG_TOP_K = int(os.getenv("RAG_TOP_K", "6"))
    RAG_LIMIAR = float(os.getenv("RAG_LIMIAR", "0.6"))  # calibrar com scripts/avaliar_rag.py
    IA_LIMITE_DIA = int(os.getenv("IA_LIMITE_DIA", "400"))

    # n8n (bônus): webhook que indexa o produto salvo no painel. Vazio = o próprio Python indexa.
    N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
    N8N_SEGREDO = os.getenv("N8N_SEGREDO", "")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # uploads de até 8 MB
