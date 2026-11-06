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

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # uploads de até 8 MB
