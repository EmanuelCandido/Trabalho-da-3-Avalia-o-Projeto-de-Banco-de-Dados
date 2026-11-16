"""Efeitos sonoros do vídeo, sintetizados (sem arquivos de terceiros), e a mixagem da trilha.

A referência não tem música nem narração: só sons de interface sincronizados com a ação e silêncio
entre eles. Cada evento da montagem (clique, tecla, whoosh, pop, tique, sucesso) vira um som aqui.
"""
import wave

import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
RNG = np.random.default_rng(7)


def _env(n, ataque, queda):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(ataque, 1e-4)) * np.exp(-t / queda)


def _banda(x, f1, f2, ordem=2):
    sos = butter(ordem, [f1 / (SR / 2), min(f2 / (SR / 2), 0.99)], btype="band", output="sos")
    return sosfilt(sos, x)


def _passa_baixa(x, f):
    return sosfilt(butter(2, f / (SR / 2), output="sos"), x)


def clique():
    n = int(0.06 * SR)
    ruido = _banda(RNG.standard_normal(n), 2500, 9000) * _env(n, 0.0004, 0.004)
    t = np.arange(n) / SR
    corpo = np.sin(2 * np.pi * 1900 * t) * _env(n, 0.0003, 0.007) * 0.5
    baixo = np.sin(2 * np.pi * 180 * t) * _env(n, 0.001, 0.012) * 0.35
    k = int(0.075 * SR)  # o "soltar" do botão, mais fraco, 75 ms depois
    x = ruido + corpo + baixo
    out = np.zeros(int(0.16 * SR))
    out[:n] += x
    out[k:k + n] += 0.45 * (ruido + corpo)[: len(out) - k]
    return out / np.max(np.abs(out))


def tecla(var):
    rng = np.random.default_rng(100 + var)
    n = int(0.05 * SR)
    f = rng.uniform(1800, 3200)
    ruido = _banda(rng.standard_normal(n), f * 0.7, f * 1.8) * _env(n, 0.0005, 0.006)
    t = np.arange(n) / SR
    baque = np.sin(2 * np.pi * rng.uniform(140, 220) * t) * _env(n, 0.001, 0.010) * 0.6
    x = ruido + baque
    return x / np.max(np.abs(x))


def whoosh(dur=0.55):
    n = int(dur * SR)
    t = np.arange(n) / SR
    base = RNG.standard_normal(n)
    # filtro passa-banda que varre: aplicado em blocos com centro variando
    out = np.zeros(n)
    blocos = 24
    for i in range(blocos):
        a, b = i * n // blocos, (i + 1) * n // blocos
        u = (a + b) / 2 / n
        centro = 300 + 1900 * np.sin(np.pi * u) ** 1.5
        seg = _banda(base[max(0, a - 2000):b], centro * 0.5, centro * 1.6)[-(b - a):]
        out[a:b] = seg
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.8
    out *= env
    return out / np.max(np.abs(out))


def pop():
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    f = 380 + 600 * np.exp(-t / 0.018)
    fase = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(fase) * _env(n, 0.001, 0.045)
    x += 0.25 * _banda(RNG.standard_normal(n), 3000, 8000) * _env(n, 0.0003, 0.003)
    return x / np.max(np.abs(x))


def tique():
    n = int(0.08 * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * 2600 * t) * _env(n, 0.0005, 0.012) + 0.4 * np.sin(2 * np.pi * 5200 * t) * _env(n, 0.0005, 0.006)
    return x / np.max(np.abs(x))


def sucesso():
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for atraso, f in [(0.0, 880.0), (0.11, 1318.5)]:
        k = int(atraso * SR)
        tt = t[: n - k]
        nota = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)) * _env(n - k, 0.004, 0.22)
        x[k:] += nota
    return x / np.max(np.abs(x))


# volume de cada tipo (dBFS de pico) — ver docs/VIDEO.md, seção 3
NIVEIS = {"clique": -10, "tecla": -19, "whoosh": -12, "pop": -13, "tique": -21, "sucesso": -11}


def mixar(cues, duracao, caminho):
    n = int((duracao + 1) * SR)
    mix = np.zeros((n, 2))
    banco = {"clique": [clique()], "tecla": [tecla(i) for i in range(8)], "whoosh": [whoosh(0.5), whoosh(0.6)],
             "pop": [pop()], "tique": [tique()], "sucesso": [sucesso()]}
    for i, c in enumerate(cues):
        variantes = banco.get(c["tipo"])
        if not variantes:
            continue
        x = variantes[i % len(variantes)] if c["tipo"] != "tecla" else variantes[RNG.integers(len(variantes))]
        ganho = 10 ** (NIVEIS[c["tipo"]] / 20) * float(c.get("vol", 1))
        if c["tipo"] == "tecla":
            ganho *= RNG.uniform(0.75, 1.1)
        # leve estéreo: teclas e cliques um pouco à direita, whoosh abre
        pan = {"tecla": 0.08, "clique": 0.05, "whoosh": 0.0}.get(c["tipo"], 0.0) + RNG.uniform(-0.05, 0.05)
        k = int(c["t"] * SR)
        if k >= n:
            continue
        m = min(len(x), n - k)
        mix[k:k + m, 0] += x[:m] * ganho * (1 - pan)
        mix[k:k + m, 1] += x[:m] * ganho * (1 + pan)
    pico = np.max(np.abs(mix)) or 1
    limite = 10 ** (-1.5 / 20)
    if pico > limite:  # limitador simples: nunca passa de -1,5 dBFS
        mix *= limite / pico
    dados = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(dados.tobytes())
    return caminho
