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


# ---------------------------------------------------------------- IA: cache de embeddings, conversa e limites

TTL_EMBEDDING = 60 * 60 * 24 * 7    # 7 dias: a mesma pergunta não chama a API de novo
TTL_CHAT = 60 * 60 * 2              # 2 horas de conversa guardada
MAX_MENSAGENS_CHAT = 8              # 4 perguntas e 4 respostas
JANELA_PERGUNTAS = 60 * 10          # limite de perguntas por visitante a cada 10 minutos


def embedding_guardado(chave):
    inicio = perf_counter()
    valor = _r.get(f"{P}ia:emb:{chave}")
    _log("GET", f"{P}ia:emb:{chave[:10]}…", "HIT" if valor else "MISS", inicio)
    return json.loads(valor) if valor else None


def guardar_embedding(chave, vetor):
    _r.set(f"{P}ia:emb:{chave}", json.dumps([round(v, 6) for v in vetor]), ex=TTL_EMBEDDING)


def historico_chat(visitante):
    """Mensagens da conversa, da mais antiga para a mais nova."""
    return [json.loads(m) for m in _r.lrange(f"{P}ia:chat:{visitante}", 0, -1)]


def adicionar_ao_chat(visitante, *mensagens):
    chave = f"{P}ia:chat:{visitante}"
    inicio = perf_counter()
    pipe = _r.pipeline()
    for m in mensagens:
        pipe.rpush(chave, json.dumps(m, ensure_ascii=False, default=str))
    pipe.ltrim(chave, -MAX_MENSAGENS_CHAT, -1)
    pipe.expire(chave, TTL_CHAT)
    pipe.execute()
    _log("RPUSH", chave, f"+{len(mensagens)}", inicio)


def limpar_chat(visitante):
    _r.delete(f"{P}ia:chat:{visitante}")


def contar_pergunta(visitante, limite):
    """INCR com TTL: devolve (pode_perguntar, segundos_para_liberar)."""
    chave = f"{P}ia:limite:{visitante}"
    pipe = _r.pipeline()
    pipe.incr(chave)
    pipe.ttl(chave)
    feitas, ttl = pipe.execute()
    if ttl is None or ttl < 0:
        _r.expire(chave, JANELA_PERGUNTAS)
        ttl = JANELA_PERGUNTAS
    return feitas <= limite, ttl


def _chave_cota(tipo):
    sufixo = "" if tipo == "chat" else f"{tipo}:"
    return f"{P}ia:cota:{sufixo}{datetime.now(timezone.utc):%Y-%m-%d}"


def cota_usada(tipo="chat"):
    return int(_r.get(_chave_cota(tipo)) or 0)


def usar_cota_do_dia(limite, tipo="chat"):
    """Conta um uso da IA no dia (teto global para não estourar o plano gratuito). O chat e a página de busca
    têm contadores separados: muita busca não deixa o chat sem resposta."""
    chave = _chave_cota(tipo)
    pipe = _r.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, 60 * 60 * 48)
    usadas = pipe.execute()[0]
    return usadas <= limite
