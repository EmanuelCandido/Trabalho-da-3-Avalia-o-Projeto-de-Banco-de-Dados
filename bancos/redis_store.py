"""Redis: vistos recentemente, carrinho, cache do catálogo, ranking de mais vistos e limite de login."""
import hashlib
import json
from collections import deque
from datetime import datetime, timezone
from time import perf_counter

import redis

P = "noma:"
TTL_VISTOS = 60 * 60 * 24 * 30      # 30 dias
TTL_CARRINHO = 60 * 60 * 24 * 7     # 7 dias
MAX_VISTOS = 12
MAX_FALHAS_LOGIN = 5
TTL_FALHAS = 60 * 15                # bloqueio de 15 minutos

_r = None
_ttl_cache = 300
eventos = deque(maxlen=40)  # últimos comandos, mostrados no dashboard do admin


def init(url, ttl_cache=300):
    global _r, _ttl_cache
    _r = redis.Redis.from_url(url, decode_responses=True, socket_timeout=4, socket_connect_timeout=4,
                              health_check_interval=30)
    _ttl_cache = ttl_cache


def cliente():
    return _r


def ping():
    return _r.ping()


def _log(comando, chave, resultado, inicio):
    eventos.appendleft({
        "comando": comando, "chave": chave, "resultado": resultado,
        "ms": round((perf_counter() - inicio) * 1000, 1),
        "hora": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------- vistos recentemente

def registrar_visto(visitante, produto_id, limite=8):
    """LREM tira o produto se já estava na lista, LPUSH põe no topo e LTRIM mantém só os 12 últimos.
    Devolve os outros vistos (sem o atual), lidos no mesmo pipeline: uma única ida ao Redis."""
    chave = f"{P}vistos:{visitante}"
    inicio = perf_counter()
    pipe = _r.pipeline()
    pipe.lrem(chave, 0, produto_id)
    pipe.lpush(chave, produto_id)
    pipe.ltrim(chave, 0, MAX_VISTOS - 1)
    pipe.expire(chave, TTL_VISTOS)
    pipe.zincrby(f"{P}ranking:views", 1, produto_id)
    pipe.lrange(chave, 1, limite)
    ids = pipe.execute()[-1]
    _log("LPUSH", chave, produto_id[-6:], inicio)
    return ids


def vistos(visitante, ignorar=None, limite=MAX_VISTOS):
    chave = f"{P}vistos:{visitante}"
    inicio = perf_counter()
    ids = _r.lrange(chave, 0, limite)
    _log("LRANGE", chave, f"{len(ids)} itens", inicio)
    return [i for i in ids if i != ignorar][:limite]


def limpar_vistos(visitante):
    _r.delete(f"{P}vistos:{visitante}")


def mais_vistos(limite=5):
    return _r.zrevrange(f"{P}ranking:views", 0, limite - 1, withscores=True)


# ---------------------------------------------------------------- carrinho

def _chave_carrinho(visitante):
    return f"{P}carrinho:{visitante}"


def chave_item(produto_id, cor="", tamanho=""):
    return f"{produto_id}|{cor or ''}|{tamanho or ''}"


def carrinho(visitante):
    """Devolve {chave_item: quantidade}."""
    dados = _r.hgetall(_chave_carrinho(visitante))
    return {k: int(v) for k, v in dados.items() if int(v) > 0}


def adicionar_item(visitante, item, quantidade):
    chave = _chave_carrinho(visitante)
    inicio = perf_counter()
    pipe = _r.pipeline()
    pipe.hincrby(chave, item, quantidade)
    pipe.expire(chave, TTL_CARRINHO)
    total = pipe.execute()[0]
    _log("HINCRBY", chave, f"+{quantidade}", inicio)
    return total


def definir_quantidade(visitante, item, quantidade):
    chave = _chave_carrinho(visitante)
    inicio = perf_counter()
    if quantidade <= 0:
        _r.hdel(chave, item)
        _log("HDEL", chave, "removido", inicio)
    else:
        _r.hset(chave, item, quantidade)
        _r.expire(chave, TTL_CARRINHO)
        _log("HSET", chave, str(quantidade), inicio)


def esvaziar_carrinho(visitante):
    _r.delete(_chave_carrinho(visitante))


# ---------------------------------------------------------------- cache do catálogo (cache-aside)

_versao_local = {"valor": None, "lida_em": 0.0}


def _versao():
    """Versão do cache. Guardada 2 s na memória do servidor para não gastar uma ida ao Redis por leitura."""
    agora = perf_counter()
    if _versao_local["valor"] is None or agora - _versao_local["lida_em"] > 2:
        _versao_local.update(valor=_r.get(f"{P}cache:versao") or "0", lida_em=agora)
    return _versao_local["valor"]


def lembrar(nome, carregar, ttl=None):
    """Cache-aside: lê do Redis (HIT) ou executa a consulta no MongoDB e grava com TTL (MISS)."""
    try:
        sufixo = hashlib.md5(nome.encode()).hexdigest()[:12] if len(nome) > 60 else nome
        chave = f"{P}cache:v{_versao()}:{sufixo}"
        inicio = perf_counter()
        pipe = _r.pipeline(transaction=False)
        pipe.get(chave)
        pipe.hincrby(f"{P}stats", "consultas", 1)
        guardado = pipe.execute()[0]
    except redis.RedisError:
        return carregar()  # sem Redis o site continua funcionando direto no MongoDB
    if guardado is not None:
        _log("GET", chave, "HIT", inicio)
        return json.loads(guardado)
    valor = carregar()
    try:
        inicio = perf_counter()
        pipe = _r.pipeline(transaction=False)
        pipe.set(chave, json.dumps(valor, default=str), ex=ttl or _ttl_cache)
        pipe.hincrby(f"{P}stats", "misses", 1)
        pipe.execute()
        _log("SET", chave, "MISS", inicio)
    except redis.RedisError:
        pass
    return valor


def invalidar_cache():
    """Novo número de versão: todas as chaves antigas deixam de ser lidas e expiram sozinhas."""
    inicio = perf_counter()
    versao = _r.incr(f"{P}cache:versao")
    _versao_local.update(valor=str(versao), lida_em=perf_counter())
    _log("INCR", f"{P}cache:versao", f"v{versao}", inicio)
    return versao


def estatisticas():
    stats = _r.hgetall(f"{P}stats")
    misses = int(stats.get("misses", 0))
    hits = max(0, int(stats.get("consultas", 0)) - misses)
    total = hits + misses
    return {"hits": hits, "misses": misses, "taxa": round(hits / total * 100) if total else 0,
            "versao": _versao(), "chaves": _r.dbsize()}


# ---------------------------------------------------------------- limite de tentativas de login

def login_bloqueado(ip):
    falhas = int(_r.get(f"{P}login:falhas:{ip}") or 0)
    if falhas >= MAX_FALHAS_LOGIN:
        return _r.ttl(f"{P}login:falhas:{ip}")
    return 0


def registrar_falha_login(ip):
    chave = f"{P}login:falhas:{ip}"
    pipe = _r.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, TTL_FALHAS)
    falhas = pipe.execute()[0]
    return max(0, MAX_FALHAS_LOGIN - falhas)


def limpar_falhas_login(ip):
    _r.delete(f"{P}login:falhas:{ip}")
